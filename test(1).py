import os
import json
import tempfile
import pickle
import random
import string
import time
import sys

# 前缀索引（按联系人姓名），索引使用联系人id
class TrieNode:
    def __init__(self):
        self.children = {}
        self.is_end_of_name = False
        # 存储联系人 id 集合，避免姓名重复导致索引冲突
        self.contact_ids = set()

class Trie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, name: str, contact_id: int):
        """将联系人姓名插入前缀树，使用 contact_id 作为标识。"""
        node = self.root
        for char in name:
            if char not in node.children:
                node.children[char] = TrieNode()
            node = node.children[char]
            node.contact_ids.add(contact_id)
        node.is_end_of_name = True

    def search_prefix(self, prefix: str) -> set:
        """返回与前缀匹配的联系人 id 集合（可能为空）。"""
        node = self.root
        for char in prefix:
            if char not in node.children:
                return set()
            node = node.children[char]
        return set(node.contact_ids)

    def delete(self, name: str, contact_id: int):
        """从前缀树中删除联系人 id 的索引引用。"""
        def _delete(node: TrieNode, name: str, depth: int) -> bool:
            if depth == len(name):
                if node.is_end_of_name:
                    node.is_end_of_name = False
                node.contact_ids.discard(contact_id)
                return len(node.children) == 0 and not node.is_end_of_name
            char = name[depth]
            if char in node.children:
                should_delete_child = _delete(node.children[char], name, depth + 1)
                if should_delete_child:
                    del node.children[char]
                node.contact_ids.discard(contact_id)
                return len(node.children) == 0 and not node.is_end_of_name
            return False

        _delete(self.root, name, 0)

# 后缀索引（按联系人电话）
class SuffixTrieNode:
    def __init__(self):
        self.children = {}
        self.is_end_of_phone = False
        # 存储联系人 id 集合，避免不同联系人同名或同号冲突
        self.contact_ids = set()


class SuffixTrie:
    def __init__(self):
        self.root = SuffixTrieNode()

    def insert(self, phone: str, contact_id: int):
        """将联系人电话插入后缀树，使用 contact_id 作为标识。"""
        node = self.root
        for char in reversed(phone):
            if char not in node.children:
                node.children[char] = SuffixTrieNode()
            node = node.children[char]
            node.contact_ids.add(contact_id)
        node.is_end_of_phone = True

    def search_suffix(self, suffix: str) -> set:
        """返回与后缀匹配的联系人 id 集合（可能为空）。"""
        node = self.root
        for char in reversed(suffix):
            if char not in node.children:
                return set()
            node = node.children[char]
        return set(node.contact_ids)

    def delete(self, phone: str, contact_id: int):
        """从后缀树中删除联系人 id 的索引引用。"""
        def _delete(node: SuffixTrieNode, phone: str, depth: int) -> bool:
            if depth == len(phone):
                if node.is_end_of_phone:
                    node.is_end_of_phone = False
                node.contact_ids.discard(contact_id)
                return len(node.children) == 0 and not node.is_end_of_phone
            char = phone[len(phone) - 1 - depth]
            if char in node.children:
                should_delete_child = _delete(node.children[char], phone, depth + 1)
                if should_delete_child:
                    del node.children[char]
                node.contact_ids.discard(contact_id)
                return len(node.children) == 0 and not node.is_end_of_phone
            return False

        _delete(self.root, phone, 0)

class ContactList:
    def __init__(self):
        self.contacts = []
        # 隐藏联系人列表（独立于正常联系人）
        self.hidden_contacts = []
        # 前缀索引（按姓名），与 contacts 中的 name 字段保持一致
        self.trie = Trie()
        # 后缀索引（按电话）
        self.suffix_trie = SuffixTrie()
        # 下一个分配的联系人唯一 id
        self.next_id = 1
        # 数据文件路径
        self.data_dir = os.path.join(os.getcwd(), "data")
        self.contacts_path = os.path.join(self.data_dir, "contacts.json")
        self.trie_path = os.path.join(self.data_dir, "trie.pkl")
        self.wal_path = os.path.join(self.data_dir, "contacts.wal")

        # 初始化持久化目录并加载状态（包含重放 WAL）
        self._ensure_data_dir()
        self._load_state()
        self._replay_wal()

#添加联系人
    def add_contact(self, name, phone_number, remark="", gender=""):
        # 检查完全重复（姓名+电话）仅在正常联系人中检查
        for c in self.contacts:
            if c.get("name") == name and c.get("phone_number") == phone_number:
                print("添加失败：已存在相同姓名和电话的联系人（重复条目）。")
                return False

        # 如果已有同名联系人，强制要求提供备注以区分（仅在正常联系人中检查）
        if any(c.get("name") == name for c in self.contacts):
            if not remark or str(remark).strip() == "":
                print("添加失败：已存在同名联系人，必须填写备注以区分。")
                return False

        # 检查手机号唯一性（不同正常联系人不能共用同一手机号）
        for c in self.contacts:
            if c.get("phone_number") == phone_number:
                print(f"添加失败：手机号 {phone_number} 已被联系人 {c.get('name')} 使用。")
                return False

        # 分配唯一 id
        contact_id = self.next_id
        self.next_id += 1

        # 记录 WAL（包含 id）并执行添加，然后持久化快照（原子替换）
        entry = {"op": "add", "data": {"id": contact_id, "name": name, "phone_number": phone_number, "remark": remark, "gender": gender, "blacklisted": False}}
        try:
            self._wal_append(entry)
        except Exception:
            print("添加失败：无法写入 WAL。")
            return False

        # 执行内存添加（不再检查 WAL）
        contact = {"id": contact_id, "name": name, "phone_number": phone_number, "remark": remark, "gender": gender, "blacklisted": False}

        # 如果备注为 "yc"（不区分大小写、两端空格），则移至隐藏联系人列表（不加入索引）
        if isinstance(remark, str) and remark.strip().lower() == "yc":
            self.hidden_contacts.append(contact)
            # 直接持久化快照并清空 WAL
            try:
                self._persist_state()
            except Exception:
                print("添加警告：已在内存中添加隐藏联系人，但持久化失败，WAL 中有未完成事务。")
                return False
            print(f"联系人 {name} 已添加至隐藏联系人列表。")
            return True

        # 正常联系人处理：加入列表并建立索引
        self.contacts.append(contact)
        try:
            self.trie.insert(name, contact_id)
        except Exception:
            pass
        try:
            self.suffix_trie.insert(phone_number, contact_id)
        except Exception:
            pass

        # 持久化快照并清空 WAL
        try:
            self._persist_state()
        except Exception:
            print("添加警告：已在内存中添加联系人，但持久化失败，WAL 中有未完成事务。")
            return False

        print(f"联系人 {name} 添加成功！")
        return True

    def search_contact(self, name):
        """按精确姓名查找联系人，返回第一个匹配的联系人字典或 None（仅在正常联系人中查找）。"""
        for c in self.contacts:
            if c.get("name") == name:
                return c
        return None

    def search_by_gender(self, gender: str):
        """按性别返回匹配的联系人列表（gender 匹配精确字符串，大小写不敏感）。"""
        if gender is None:
            return []
        g = gender.strip().lower()
        results = [c for c in self.contacts if str(c.get("gender", "")).strip().lower() == g]
        return results

#删除联系人
    def delete_contact(self, name):
        contact = self.search_contact(name)
        if not contact:
            print(f"不存在 {name}，删除失败")
            return False

        # 写 WAL（包含 id）
        contact_id = contact.get("id")
        entry = {"op": "delete", "data": {"id": contact_id, "name": name}}
        try:
            self._wal_append(entry)
        except Exception:
            print("删除失败：无法写入 WAL。")
            return False

        # 执行内存删除
        old_phone = contact.get("phone_number")
        try:
            self.contacts.remove(contact)
        except Exception:
            pass
        try:
            self.trie.delete(name, contact_id)
        except Exception:
            pass
        try:
            if old_phone:
                self.suffix_trie.delete(old_phone, contact_id)
        except Exception:
            pass

        # 持久化快照并清空 WAL
        try:
            self._persist_state()
        except Exception:
            print("删除警告：内存已删除，但持久化失败，WAL 中有未完成事务。")
            return False

        print(f"联系人 {name} 删除成功！")
        return True

#修改联系人信息
    def edit_contact(self, name, new_name=None, new_phone=None, new_remark=None, new_gender=None):
        contact = self.search_contact(name)
        if not contact:
            print(f"未找到联系人：{name}")
            return False
        # 写 WAL（包含 id）
        contact_id = contact.get("id")
        entry = {"op": "edit", "data": {"id": contact_id, "name": name, "new_name": new_name, "new_phone": new_phone, "new_remark": new_remark, "new_gender": new_gender}}
        try:
            self._wal_append(entry)
        except Exception:
            print("修改失败：无法写入 WAL。")
            return False

        # 执行内存修改
        old_name = contact.get("name")
        old_phone = contact.get("phone_number")
        old_gender = contact.get("gender")

        # 计算最终要设置的值
        final_name = old_name if new_name is None else new_name
        final_phone = old_phone if new_phone is None else new_phone
        final_gender = old_gender if new_gender is None else new_gender

        # 如果将姓名修改为已存在的姓名，强制要求填写备注（new_remark 必须非空）
        if new_name is not None and new_name != old_name:
            if any(c.get("name") == new_name and c.get("id") != contact_id for c in self.contacts):
                if not new_remark or str(new_remark).strip() == "":
                    print("修改失败：目标姓名与已有联系人重复，必须填写备注以区分。")
                    return False

        # 如果要修改手机号，先检查唯一性
        if new_phone is not None and new_phone != old_phone:
            for c in self.contacts:
                if c.get("id") != contact_id and c.get("phone_number") == new_phone:
                    print(f"修改失败：手机号 {new_phone} 已被联系人 {c.get('name')} 使用。")
                    return False

        # 应用索引变更（使用 id）
        try:
            if new_name is not None and new_name != old_name:
                try:
                    self.trie.delete(old_name, contact_id)
                except Exception:
                    pass
                try:
                    self.trie.insert(final_name, contact_id)
                except Exception:
                    pass
            if new_phone is not None and new_phone != old_phone:
                try:
                    if old_phone:
                        self.suffix_trie.delete(old_phone, contact_id)
                except Exception:
                    pass
                try:
                    if final_phone:
                        self.suffix_trie.insert(final_phone, contact_id)
                except Exception:
                    pass
        except Exception:
            pass

        # 更新联系人内容
        contact["name"] = final_name
        contact["phone_number"] = final_phone
        if new_remark is not None:
            contact["remark"] = new_remark
        if new_gender is not None:
            contact["gender"] = new_gender

        # 持久化快照并清空 WAL
        try:
            self._persist_state()
        except Exception:
            print("修改警告：内存已修改，但持久化失败，WAL 中有未完成事务。")
            return False

        print(f"联系人 {name} 已更新。")
        return True

    def search_by_prefix(self, prefix):
        """使用前缀索引返回匹配的联系人列表。"""
        ids = self.trie.search_prefix(prefix)
        if not ids:
            return []
        results = [c for c in self.contacts if c.get("id") in ids]
        return results

    def search_by_phone_suffix(self, suffix):
        """使用后缀索引返回匹配的联系人列表（按电话后缀）。"""
        ids = self.suffix_trie.search_suffix(suffix)
        if not ids:
            return []
        results = [c for c in self.contacts if c.get("id") in ids]
        return results

#列出所有联系人
    def list_contacts(self):
        if not self.contacts:
            print("联系人列表为空。")
            return
        for i, c in enumerate(self.contacts, start=1):
            status = "黑名单" if c.get("blacklisted") else "正常"
            print(f"{i}. 名称: {c.get('name')}, 电话: {c.get('phone_number')}, 性别: {c.get('gender')}, 状态: {status}, 备注: {c.get('remark')}")

    def list_hidden_contacts(self):
        """列出隐藏联系人（独立列表）。"""
        if not self.hidden_contacts:
            print("隐藏联系人列表为空。")
            return
        for i, c in enumerate(self.hidden_contacts, start=1):
            status = "黑名单" if c.get("blacklisted") else "隐藏"
            print(f"{i}. 名称: {c.get('name')}, 电话: {c.get('phone_number')}, 性别: {c.get('gender')}, 状态: {status}, 备注: {c.get('remark')}")

    def sort_contacts_by_initial(self):
        """按姓名首字母（首字符）排序联系人列表，修改原列表顺序。"""
        def sort_key(c):
            name = c.get("name") or ""
            if name == "":
                return ("~", "")
            first = name[0]
            try:
                # 英文字母按不区分大小写排序；其他字符按原顺序（Unicode）
                first_key = first.upper()
            except Exception:
                first_key = first
            return (first_key, name)

        self.contacts.sort(key=sort_key)
        print("联系人已按姓名首字母排序。")

    # ---------- 持久化相关方法（WAL + 原子快照） ----------
    def _ensure_data_dir(self):
        if not os.path.isdir(self.data_dir):
            try:
                os.makedirs(self.data_dir, exist_ok=True)
            except Exception:
                pass

    def _wal_append(self, entry: dict):
        """将操作追加到 WAL 并确保写入磁盘。"""
        with open(self.wal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _atomic_write_json(self, path, obj):
        dirpath = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=dirpath)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tf:
                json.dump(obj, tf, ensure_ascii=False, indent=2)
                tf.flush()
                os.fsync(tf.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    def _atomic_write_pickle(self, path, obj):
        dirpath = os.path.dirname(path)
        fd, tmp = tempfile.mkstemp(dir=dirpath)
        try:
            with os.fdopen(fd, "wb") as tf:
                pickle.dump(obj, tf)
                tf.flush()
                os.fsync(tf.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass

    def _persist_state(self):
        """写入 contacts.json 和 trie.pkl 的原子快照，并在成功后清空 WAL。"""
        # 写 contacts（包含隐藏列表）
        try:
            self._atomic_write_json(self.contacts_path, {"contacts": self.contacts, "hidden_contacts": self.hidden_contacts})
        except Exception as e:
            raise

        # 写 trie（pickle 序列化内存结构）
        try:
            self._atomic_write_pickle(self.trie_path, {"trie": self.trie, "suffix_trie": self.suffix_trie})
        except Exception:
            raise

        # 成功后清空 WAL（truncate）
        try:
            with open(self.wal_path, "w", encoding="utf-8") as f:
                f.truncate(0)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            pass

    def _load_state(self):
        """加载 contacts.json 与 trie.pkl（若存在）。"""
        # 加载联系人数据
        try:
            if os.path.exists(self.contacts_path):
                with open(self.contacts_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.contacts = data.get("contacts", []) or []
                    self.hidden_contacts = data.get("hidden_contacts", []) or []
        except Exception:
            self.contacts = []
            self.hidden_contacts = []

        # 更新 next_id 基准（确保 id 不会重复）
        try:
            max_id = 0
            for c in self.contacts + self.hidden_contacts:
                cid = c.get("id")
                if isinstance(cid, int) and cid > max_id:
                    max_id = cid
            if max_id >= self.next_id:
                self.next_id = max_id + 1
        except Exception:
            pass

        # 如果存在，加载 trie 快照
        try:
            if os.path.exists(self.trie_path):
                with open(self.trie_path, "rb") as f:
                    obj = pickle.load(f)
                    self.trie = obj.get("trie", self.trie)
                    self.suffix_trie = obj.get("suffix_trie", self.suffix_trie)
        except Exception:
            pass

    def _replay_wal(self):
        """读取并重放 WAL 中的操作（若存在），以恢复未完成事务。"""
        if not os.path.exists(self.wal_path):
            return
        try:
            with open(self.wal_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
        except Exception:
            return

        if not lines:
            return

        # 重放每一条操作
        for ln in lines:
            try:
                entry = json.loads(ln)
            except Exception:
                continue
            op = entry.get("op")
            data = entry.get("data", {})
            try:
                if op == "add":
                    cid = data.get("id")
                    contact = {"id": cid, "name": data.get("name"), "phone_number": data.get("phone_number"), "remark": data.get("remark"), "gender": data.get("gender"), "blacklisted": data.get("blacklisted", False)}
                    # 如果备注为 yc 则放隐藏列表
                    if isinstance(contact.get("remark"), str) and contact.get("remark").strip().lower() == "yc":
                        # avoid duplicates by id
                        if not any(c.get("id") == cid for c in self.hidden_contacts):
                            self.hidden_contacts.append(contact)
                    else:
                        if not any(c.get("id") == cid for c in self.contacts):
                            self.contacts.append(contact)
                            try:
                                self.trie.insert(contact.get("name", ""), cid)
                            except Exception:
                                pass
                            try:
                                if contact.get("phone_number"):
                                    self.suffix_trie.insert(contact.get("phone_number"), cid)
                            except Exception:
                                pass
                elif op == "delete":
                    cid = data.get("id")
                    # 从正常联系人中删除
                    to_remove = [c for c in self.contacts if c.get("id") == cid]
                    for c in to_remove:
                        try:
                            self.trie.delete(c.get("name", ""), cid)
                        except Exception:
                            pass
                        try:
                            if c.get("phone_number"):
                                self.suffix_trie.delete(c.get("phone_number"), cid)
                        except Exception:
                            pass
                        try:
                            self.contacts.remove(c)
                        except Exception:
                            pass
                    # 也尝试从隐藏联系人中删除
                    to_remove_hidden = [c for c in self.hidden_contacts if c.get("id") == cid]
                    for c in to_remove_hidden:
                        try:
                            self.hidden_contacts.remove(c)
                        except Exception:
                            pass
                elif op == "edit":
                    cid = data.get("id")
                    # 查找在正常联系人列表中
                    target = next((c for c in self.contacts if c.get("id") == cid), None)
                    in_hidden = False
                    if not target:
                        target = next((c for c in self.hidden_contacts if c.get("id") == cid), None)
                        in_hidden = True if target else False
                    if target:
                        old_name = target.get("name")
                        old_phone = target.get("phone_number")
                        new_name = data.get("new_name')") if False else data.get("new_name")
                        # apply fields if present
                        if data.get("new_name") is not None:
                            # update trie if in normal contacts
                            if not in_hidden:
                                try:
                                    self.trie.delete(old_name, cid)
                                except Exception:
                                    pass
                                try:
                                    self.trie.insert(data.get("new_name"), cid)
                                except Exception:
                                    pass
                            target["name"] = data.get("new_name")
                        if data.get("new_phone") is not None:
                            if not in_hidden:
                                try:
                                    if old_phone:
                                        self.suffix_trie.delete(old_phone, cid)
                                except Exception:
                                    pass
                                try:
                                    if data.get("new_phone"):
                                        self.suffix_trie.insert(data.get("new_phone"), cid)
                                except Exception:
                                    pass
                            target["phone_number"] = data.get("new_phone")
                        if data.get("new_remark") is not None:
                            target["remark"] = data.get("new_remark")
                        if data.get("new_gender") is not None:
                            target["gender"] = data.get("new_gender")
                        # Note: do not auto-move between hidden/normal on WAL replay (keeps behavior simple)
                elif op == "blacklist":
                    cid = data.get("id")
                    for lst in (self.contacts, self.hidden_contacts):
                        for c in lst:
                            if c.get("id") == cid:
                                c["blacklisted"] = bool(data.get("blacklisted", False))
            except Exception:
                continue

        # 重放完成后，保存一次快照并清空 WAL
        try:
            self._persist_state()
        except Exception:
            pass

    # ---------- 黑名单相关方法 ----------
    def set_blacklist(self, name, blacklisted=True):
        """根据姓名设置黑名单状态（写 WAL 并持久化）。"""
        contact = self.search_contact(name)
        if not contact:
            print(f"未找到联系人：{name}")
            return False
        cid = contact.get("id")
        entry = {"op": "blacklist", "data": {"id": cid, "blacklisted": bool(blacklisted)}}
        try:
            self._wal_append(entry)
        except Exception:
            print("操作失败：无法写入 WAL。")
            return False

        contact["blacklisted"] = bool(blacklisted)
        try:
            self._persist_state()
        except Exception:
            print("警告：内存已更新，但持久化失败，WAL 中有未完成事务。")
            return False

        state = "已加入黑名单" if contact.get("blacklisted") else "已移出黑名单"
        print(f"联系人 {contact.get('name')} {state}。")
        return True

 # ----------------- Trie 性能基准工具 -----------------
def _random_name(min_len=3, max_len=10):
    return "".join(random.choices(string.ascii_lowercase, k=random.randint(min_len, max_len)))

def bench_trie(n=20000, q=200, seed=42):
    """在内存中对 Trie 与朴素 startswith 做插入/查询/删除性能对比。"""
    random.seed(seed)
    names = [_random_name() for _ in range(n)]

    trie = Trie()

    # trie 插入基准测试
    t0 = time.perf_counter()
    for i, name in enumerate(names):
        trie.insert(name, i)
    t_insert_trie = time.perf_counter() - t0

    # 生成查询用的随机前缀
    prefixes = [names[random.randrange(n)][: random.randint(1, 4)] for _ in range(q)]

    # trie 前缀查询基准
    t0 = time.perf_counter()
    for p in prefixes:
        _ = trie.search_prefix(p)
    t_query_trie = time.perf_counter() - t0

    # 朴素前缀扫描查询基准
    t0 = time.perf_counter()
    for p in prefixes:
        for name in names:
            if name.startswith(p):
                pass
    t_query_naive = time.perf_counter() - t0

    # trie 删除基准测试
    t0 = time.perf_counter()
    for i, name in enumerate(names):
        trie.delete(name, i)
    t_delete_trie = time.perf_counter() - t0

    def ms(x):
        return f"{x*1000:.2f} ms"

    print("\nTrie 性能基准结果：")
    print(f"  items: {n}, queries: {q}")
    print(f"  插入 - trie: {ms(t_insert_trie)}")
    print(f"  前缀查询 - trie: {ms(t_query_trie)}, 朴素扫描: {ms(t_query_naive)}")
    print(f"  删除 - trie: {ms(t_delete_trie)}")
    


if __name__=="__main__":
    cl = ContactList()
    while True:
        print("\n通讯录存储与检索系统")
        print("1. 添加联系人")
        print("2. 查找联系人")
        print("3. 删除联系人")
        print("4. 修改联系人信息")
        print("5. 列出所有联系人")
        print("6. 退出系统")
        print("7. Trie 性能基准测试")
        choice = input("请选择操作选项：").strip()

        if choice == "1":
            name = input("请输入联系人姓名：")
            phone_number = input("请输入联系人电话：")
            gender = input("请输入性别（可选）：").strip()
            remark = input("请输入备注（可选,不输入默认空白）：")
            cl.add_contact(name,phone_number,remark,gender)
        
        elif choice == "2":
            print("查找方式：1. 按全名  2. 按姓名前缀  3. 按手机号后缀  4. 按性别")
            mode = input("请选择查找方式(1/2/3/4)：").strip()
            if mode == "1":
                name = input("请输入要查找的联系人姓名：")
                contact = cl.search_contact(name)
                if contact:
                    print(f"找到联系人：名称: {contact.get('name')}, 电话: {contact.get('phone_number')}, 性别: {contact.get('gender')}, 备注: {contact.get('remark')}")
                else:
                    print("未找到联系人（隐藏联系人不会在正常查询中显示）。")
            elif mode == "2":
                prefix = input("请输入姓名前缀：")
                results = cl.search_by_prefix(prefix)
                if not results:
                    print("未找到匹配的联系人。")
                else:
                    for c in results:
                        print(f"名称: {c.get('name')}, 电话: {c.get('phone_number')}, 备注: {c.get('remark')}")
            elif mode == "3":
                suffix = input("请输入手机号后缀（例如尾号）：")
                results = cl.search_by_phone_suffix(suffix)
                if not results:
                    print("未找到匹配的联系人。")
                else:
                    for c in results:
                        print(f"名称: {c.get('name')}, 电话: {c.get('phone_number')}, 备注: {c.get('remark')}")
            elif mode == "4":
                gender_q = input("请输入要查询的性别：").strip()
                results = cl.search_by_gender(gender_q)
                if not results:
                    print("未找到匹配的联系人。")
                else:
                    for c in results:
                        print(f"名称: {c.get('name')}, 电话: {c.get('phone_number')}, 备注: {c.get('remark')}")
            else:
                print("无效的查找方式。")
        
        elif choice == "3":
            name = input("请输入联系人姓名：")
            cl.delete_contact(name)

        elif choice == "4":
            name = input("请输入联系人姓名：")
            contact = cl.search_contact(name)
            if not contact:
                print("该联系人不存在")
            else:
                print(f"当前信息：名称: {contact.get('name')}, 电话: {contact.get('phone_number')}, 性别: {contact.get('gender')}, 备注: {contact.get('remark')}")
                new_name = input("请输入新的姓名（回车保留不变）：").strip()
                new_phone = input("请输入新的电话（回车保留不变）：").strip()
                new_remark = input("请输入新的备注（回车保留不变）：").strip()
                new_gender = input("请输入新的性别（回车保留不变）：").strip()
                if new_name == "":
                    new_name = None
                if new_phone == "":
                    new_phone = None
                if new_remark == "":
                    new_remark = None
                if new_gender == "":
                    new_gender = None
                cl.edit_contact(name, new_name, new_phone, new_remark, new_gender)
            
        elif choice == "5":
            cl.list_contacts()
        
        elif choice == "6":
            print("再见！")
            break

        elif choice == "7":
            try:
                n_in = input("请输入要生成的名字数量 n（回车使用默认20000）：").strip()
                q_in = input("请输入要执行的查询次数 q（回车使用默认200）：").strip()
                n = int(n_in) if n_in else 20000
                q = int(q_in) if q_in else 200
            except Exception:
                print("输入无效，使用默认参数 n=20000, q=200")
                n, q = 20000, 200
            bench_trie(n=n, q=q)

        elif choice == "666":
            cl.list_hidden_contacts()

        else:
            print("输入错误，请重新输入。")
