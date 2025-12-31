#!/usr/bin/env python3
"""
通讯录程序：顺序存储联系人 + Trie 索引 + WAL 原子持久化 + 命令行交互

功能亮点：
- 联系人信息：姓名、电话、备注
- 支持插入、删除、更新、遍历
- 基于 Trie 加速姓名/电话前缀检索
- 处理重名/重复号码规则：允许同名、电话号码唯一；重复电话插入被拒绝
- 使用写前日志（WAL）+ 原子快照保证持久化原子性与崩溃恢复
- 提供性能对比测试：线性检索 vs Trie 检索

使用：运行 `python3 src/contact_app.py` 后进入交互命令行，输入 `help` 查看命令
"""

import os
import json
import time
import tempfile
from typing import Dict, List, Optional, Set


class Contact:
    def __init__(self, cid: int, name: str, phone: str, note: str = ""):
        self.id = cid
        self.name = name
        self.phone = phone
        self.note = note

    def to_dict(self):
        return {"id": self.id, "name": self.name, "phone": self.phone, "note": self.note}

    @staticmethod
    def from_dict(d):
        return Contact(d["id"], d["name"], d["phone"], d.get("note", ""))


class TrieNode:
    def __init__(self):
        self.children: Dict[str, "TrieNode"] = {}
        self.ids: Set[int] = set()


class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, key: str, cid: int):
        node = self.root
        for ch in key:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
            node.ids.add(cid)

    def remove(self, key: str, cid: int):
        node = self.root
        stack = []
        for ch in key:
            if ch not in node.children:
                return
            stack.append((node, ch))
            node = node.children[ch]
        # remove id from path
        for parent, ch in stack:
            child = parent.children[ch]
            child.ids.discard(cid)
            # optional: prune empty nodes to save memory
            if not child.ids and not child.children:
                del parent.children[ch]

    def prefix_search(self, prefix: str) -> Set[int]:
        node = self.root
        for ch in prefix:
            if ch not in node.children:
                return set()
            node = node.children[ch]
        return set(node.ids)


class ContactManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.snapshot_file = os.path.join(self.data_dir, "contacts.json")
        self.wal_file = os.path.join(self.data_dir, "contacts.wal")

        self.contacts: List[Contact] = []
        self.phone_index: Dict[str, int] = {}  # phone -> contact id index in self.contacts
        self.name_trie = Trie()
        self.phone_trie = Trie()
        self.next_id = 1

        self._load_snapshot()
        self._replay_wal()

    # ---------- persistence helpers (WAL + snapshot) ----------
    def _fsync_file(self, f):
        f.flush()
        os.fsync(f.fileno())

    def _append_wal(self, entry: Dict):
        with open(self.wal_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self._fsync_file(f)

    def _write_snapshot(self):
        tmpfd, tmpname = tempfile.mkstemp(dir=self.data_dir, prefix="snapshot_", text=True)
        try:
            with os.fdopen(tmpfd, "w", encoding="utf-8") as f:
                data = {"next_id": self.next_id, "contacts": [c.to_dict() for c in self.contacts]}
                json.dump(data, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmpname, self.snapshot_file)
            # snapshot installed; WAL can be truncated
            with open(self.wal_file, "w", encoding="utf-8") as f:
                f.truncate(0)
                self._fsync_file(f)
        finally:
            if os.path.exists(tmpname):
                try:
                    os.remove(tmpname)
                except OSError:
                    pass

    def _load_snapshot(self):
        if not os.path.exists(self.snapshot_file):
            return
        with open(self.snapshot_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.next_id = data.get("next_id", 1)
        self.contacts = [Contact.from_dict(d) for d in data.get("contacts", [])]
        # rebuild indexes
        self.phone_index = {}
        self.name_trie = Trie()
        self.phone_trie = Trie()
        for c in self.contacts:
            self.phone_index[c.phone] = c.id
            self.name_trie.insert(c.name, c.id)
            self.phone_trie.insert(c.phone, c.id)

    def _replay_wal(self):
        if not os.path.exists(self.wal_file):
            return
        applied = False
        with open(self.wal_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                op = entry.get("op")
                data = entry.get("data")
                if op == "add":
                    self._apply_add_replay(data)
                    applied = True
                elif op == "delete":
                    self._apply_delete_replay(data)
                    applied = True
                elif op == "update":
                    self._apply_update_replay(data)
                    applied = True
        if applied:
            # after replaying, write a fresh snapshot and clear WAL
            self._write_snapshot()

    # replay helpers (do not write WAL again)
    def _apply_add_replay(self, data):
        c = Contact(data["id"], data["name"], data["phone"], data.get("note", ""))
        self.contacts.append(c)
        self.phone_index[c.phone] = c.id
        self.name_trie.insert(c.name, c.id)
        self.phone_trie.insert(c.phone, c.id)
        self.next_id = max(self.next_id, c.id + 1)

    def _apply_delete_replay(self, data):
        cid = data["id"]
        # remove contact by id (id unique)
        for i, c in enumerate(self.contacts):
            if c.id == cid:
                self.name_trie.remove(c.name, c.id)
                self.phone_trie.remove(c.phone, c.id)
                self.phone_index.pop(c.phone, None)
                self.contacts.pop(i)
                break

    def _apply_update_replay(self, data):
        cid = data["id"]
        for c in self.contacts:
            if c.id == cid:
                # remove old trie indexes if name/phone changed
                old_name = c.name
                old_phone = c.phone
                new_name = data.get("name", c.name)
                new_phone = data.get("phone", c.phone)
                new_note = data.get("note", c.note)
                if old_name != new_name:
                    self.name_trie.remove(old_name, c.id)
                    self.name_trie.insert(new_name, c.id)
                    c.name = new_name
                if old_phone != new_phone:
                    self.phone_trie.remove(old_phone, c.id)
                    self.phone_trie.insert(new_phone, c.id)
                    self.phone_index.pop(old_phone, None)
                    self.phone_index[new_phone] = c.id
                    c.phone = new_phone
                c.note = new_note
                break

    # ---------- core operations (ensure WAL + snapshot atomicity) ----------
    def add_contact(self, name: str, phone: str, note: str = "") -> Optional[int]:
        # phone must be unique
        if phone in self.phone_index:
            return None
        cid = self.next_id
        entry = {"op": "add", "data": {"id": cid, "name": name, "phone": phone, "note": note}}
        self._append_wal(entry)
        # apply in-memory
        c = Contact(cid, name, phone, note)
        self.contacts.append(c)
        self.phone_index[phone] = cid
        self.name_trie.insert(name, cid)
        self.phone_trie.insert(phone, cid)
        self.next_id += 1
        # snapshot and truncate wal atomically
        self._write_snapshot()
        return cid

    def delete_contact_by_phone(self, phone: str) -> bool:
        cid = self.phone_index.get(phone)
        if cid is None:
            return False
        entry = {"op": "delete", "data": {"id": cid}}
        self._append_wal(entry)
        # apply
        for i, c in enumerate(self.contacts):
            if c.id == cid:
                self.name_trie.remove(c.name, c.id)
                self.phone_trie.remove(c.phone, c.id)
                self.phone_index.pop(c.phone, None)
                self.contacts.pop(i)
                break
        self._write_snapshot()
        return True

    def update_contact(self, phone: str, name: Optional[str] = None, new_phone: Optional[str] = None, note: Optional[str] = None) -> bool:
        cid = self.phone_index.get(phone)
        if cid is None:
            return False
        # if changing phone ensure uniqueness
        if new_phone and new_phone != phone and new_phone in self.phone_index:
            return False
        entry = {"op": "update", "data": {"id": cid}}
        if name is not None:
            entry["data"]["name"] = name
        if new_phone is not None:
            entry["data"]["phone"] = new_phone
        if note is not None:
            entry["data"]["note"] = note
        self._append_wal(entry)
        # apply
        for c in self.contacts:
            if c.id == cid:
                old_name = c.name
                old_phone = c.phone
                if name is not None and name != old_name:
                    self.name_trie.remove(old_name, c.id)
                    self.name_trie.insert(name, c.id)
                    c.name = name
                if new_phone is not None and new_phone != old_phone:
                    self.phone_trie.remove(old_phone, c.id)
                    self.phone_trie.insert(new_phone, c.id)
                    self.phone_index.pop(old_phone, None)
                    self.phone_index[new_phone] = c.id
                    c.phone = new_phone
                if note is not None:
                    c.note = note
                break
        self._write_snapshot()
        return True

    def list_contacts(self) -> List[Dict]:
        return [c.to_dict() for c in self.contacts]

    def find_by_name_prefix(self, prefix: str) -> List[Dict]:
        ids = self.name_trie.prefix_search(prefix)
        res = []
        id_to_contact = {c.id: c for c in self.contacts}
        for cid in sorted(ids):
            if cid in id_to_contact:
                res.append(id_to_contact[cid].to_dict())
        return res

    def find_by_phone_prefix(self, prefix: str) -> List[Dict]:
        ids = self.phone_trie.prefix_search(prefix)
        res = []
        id_to_contact = {c.id: c for c in self.contacts}
        for cid in sorted(ids):
            if cid in id_to_contact:
                res.append(id_to_contact[cid].to_dict())
        return res

    # fallback linear scan (用于性能对比)
    def linear_search_name_prefix(self, prefix: str) -> List[Dict]:
        res = []
        for c in self.contacts:
            if c.name.startswith(prefix):
                res.append(c.to_dict())
        return res

    def linear_search_phone_prefix(self, prefix: str) -> List[Dict]:
        res = []
        for c in self.contacts:
            if c.phone.startswith(prefix):
                res.append(c.to_dict())
        return res


def run_perf_test(manager: ContactManager, n: int = 2000):
    import random
    import string

    # generate random contacts
    print(f"生成 {n} 条随机联系人用于性能测试...")
    names = []
    phones = []
    for i in range(n):
        name = "".join(random.choices(string.ascii_lowercase, k=8))
        phone = ''.join(random.choices(string.digits, k=11))
        names.append(name)
        phones.append(phone)

    # clear manager data for test
    manager.contacts = []
    manager.phone_index = {}
    manager.name_trie = Trie()
    manager.phone_trie = Trie()
    manager.next_id = 1

    for name, phone in zip(names, phones):
        manager.add_contact(name, phone)

    # choose random prefixes
    prefixes = [names[i][:k] for i, k in zip(range(0, min(200, n)), [3]*min(200, n))]
    # measure linear vs trie for name prefix
    def time_fn(fn, args, repeats=3):
        t0 = time.perf_counter()
        for _ in range(repeats):
            for p in prefixes:
                fn(p)
        t1 = time.perf_counter()
        return (t1 - t0) / repeats

    linear_time = time_fn(manager.linear_search_name_prefix, (prefixes,))
    trie_time = time_fn(manager.find_by_name_prefix, (prefixes,))

    report = {
        "n": n,
        "prefixes_tested": len(prefixes),
        "linear_name_time_s": linear_time,
        "trie_name_time_s": trie_time,
    }
    print("性能测试结果：")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # 写入报告
    rpt_file = os.path.join(manager.data_dir, "perf_report.json")
    with open(rpt_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"报告已保存：{rpt_file}")


def repl():
    mgr = ContactManager()
    print("欢迎使用通讯录。输入 help 查看命令。")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]
        if cmd in ("exit", "quit"):
            break
        elif cmd == "help":
            print("命令：add name phone [note] | del phone | update phone [name=newname] [phone=newphone] [note=newnote] | list | find_name prefix | find_phone prefix | perf [n] | help | exit")
        elif cmd == "add":
            if len(args) < 2:
                print("用法: add 姓名 电话 [备注]")
                continue
            name = args[0]
            phone = args[1]
            note = " ".join(args[2:]) if len(args) > 2 else ""
            cid = mgr.add_contact(name, phone, note)
            if cid is None:
                print("失败：电话号码已存在。")
            else:
                print(f"添加成功，id={cid}")
        elif cmd == "del":
            if len(args) != 1:
                print("用法: del 电话")
                continue
            ok = mgr.delete_contact_by_phone(args[0])
            print("删除成功" if ok else "未找到该电话")
        elif cmd == "update":
            if len(args) < 1:
                print("用法: update oldphone [name=newname] [phone=newphone] [note=newnote]")
                continue
            oldphone = args[0]
            kw = {}
            for a in args[1:]:
                if '=' in a:
                    k, v = a.split('=', 1)
                    kw[k] = v
            ok = mgr.update_contact(oldphone, name=kw.get('name'), new_phone=kw.get('phone'), note=kw.get('note'))
            print("更新成功" if ok else "更新失败（可能电话号码冲突或未找到）")
        elif cmd == "list":
            for c in mgr.list_contacts():
                print(c)
        elif cmd == "find_name":
            if len(args) != 1:
                print("用法: find_name 前缀")
                continue
            res = mgr.find_by_name_prefix(args[0])
            for c in res:
                print(c)
        elif cmd == "find_phone":
            if len(args) != 1:
                print("用法: find_phone 前缀")
                continue
            res = mgr.find_by_phone_prefix(args[0])
            for c in res:
                print(c)
        elif cmd == "perf":
            n = int(args[0]) if args and args[0].isdigit() else 2000
            run_perf_test(mgr, n=n)
        else:
            print("未知命令，输入 help 查看可用命令")


if __name__ == "__main__":
    repl()
