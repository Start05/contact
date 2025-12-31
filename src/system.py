import os
import json
import pickle
import tempfile
from trie import Trie, SuffixTrie


class ContactList:
    def __init__(self):
        self.contacts = []
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
    def add_contact(self, name, phone_number, remark=""):
        """
        添加联系人并同步索引。

        处理规则：
        - 手机号必须唯一：如果手机号已存在则拒绝添加并提示（防止误合并）。
        - 姓名可以重复（允许重名），内部通过唯一 `id` 索引以支持重名查找。
        - 若姓名和手机号完全都与已有联系人一致，视为重复条目，拒绝添加。
        """
        # 检查完全重复（姓名+电话）
        for c in self.contacts:
            if c.get("name") == name and c.get("phone_number") == phone_number:
                print("添加失败：已存在相同姓名和电话的联系人（重复条目）。")
                return False

        # 如果已有同名联系人，强制要求提供备注以区分
        if any(c.get("name") == name for c in self.contacts):
            if not remark or str(remark).strip() == "":
                print("添加失败：已存在同名联系人，必须填写备注以区分。")
                return False

        # 检查手机号唯一性（不同联系人不能共用同一手机号）
        for c in self.contacts:
            if c.get("phone_number") == phone_number:
                print(f"添加失败：手机号 {phone_number} 已被联系人 {c.get('name')} 使用。")
                return False

        # 分配唯一 id
        contact_id = self.next_id
        self.next_id += 1

        # 记录 WAL（包含 id）并执行添加，然后持久化快照（原子替换）
        entry = {"op": "add", "data": {"id": contact_id, "name": name, "phone_number": phone_number, "remark": remark}}
        try:
            self._wal_append(entry)
        except Exception:
            print("添加失败：无法写入 WAL。")
            return False

        # 执行内存添加（不再检查 WAL）
        contact = {"id": contact_id, "name": name, "phone_number": phone_number, "remark": remark}
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
        """按精确姓名查找联系人，返回第一个匹配的联系人字典或 None。"""
        for c in self.contacts:
            if c.get("name") == name:
                return c
        return None

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
    def edit_contact(self, name, new_name=None, new_phone=None, new_remark=None):
        contact = self.search_contact(name)
        if not contact:
            print(f"未找到联系人：{name}")
            return False
        # 写 WAL（包含 id）
        contact_id = contact.get("id")
        entry = {"op": "edit", "data": {"id": contact_id, "name": name, "new_name": new_name, "new_phone": new_phone, "new_remark": new_remark}}
        try:
            self._wal_append(entry)
        except Exception:
            print("修改失败：无法写入 WAL。")
            return False

        # 执行内存修改
        old_name = contact.get("name")
        old_phone = contact.get("phone_number")

        # 计算最终要设置的值
        final_name = old_name if new_name is None else new_name
        final_phone = old_phone if new_phone is None else new_phone

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
            print(f"{i}. 名称: {c.get('name')}, 电话: {c.get('phone_number')}, 备注: {c.get('remark')}")

        # （图片生成功能已移除，保持文本输出）

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
        # 写 contacts
        try:
            self._atomic_write_json(self.contacts_path, {"contacts": self.contacts})
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
        # load contacts
        try:
            if os.path.exists(self.contacts_path):
                with open(self.contacts_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.contacts = data.get("contacts", [])
        except Exception:
            self.contacts = []

        # 更新 next_id 基准（确保 id 不会重复）
        try:
            max_id = 0
            for c in self.contacts:
                cid = c.get("id")
                if isinstance(cid, int) and cid > max_id:
                    max_id = cid
            if max_id >= self.next_id:
                self.next_id = max_id + 1
        except Exception:
            pass

        # load trie snapshot if exists
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
                    # 使用 WAL 中的 id（若存在），避免重复添加
                    wid = data.get("id")
                    exists = any(c.get("id") == wid for c in self.contacts if wid is not None)
                    if not exists:
                        # 如果没有 id，则分配新 id
                        if wid is None:
                            wid = self.next_id
                            self.next_id += 1
                        else:
                            # 确保 next_id 大于已使用 id
                            if wid >= self.next_id:
                                self.next_id = wid + 1
                        contact = {"id": wid, "name": data.get("name"), "phone_number": data.get("phone_number"), "remark": data.get("remark")}
                        self.contacts.append(contact)
                        try:
                            self.trie.insert(contact.get("name"), contact.get("id"))
                        except Exception:
                            pass
                        try:
                            self.suffix_trie.insert(contact.get("phone_number"), contact.get("id"))
                        except Exception:
                            pass
                elif op == "delete":
                    cid = data.get("id")
                    contact = None
                    if cid is not None:
                        contact = next((c for c in self.contacts if c.get("id") == cid), None)
                    else:
                        # fallback by name
                        name = data.get("name")
                        contact = next((c for c in self.contacts if c.get("name") == name), None)
                    if contact:
                        try:
                            self.contacts.remove(contact)
                        except Exception:
                            pass
                        try:
                            self.trie.delete(contact.get("name"), contact.get("id"))
                        except Exception:
                            pass
                        try:
                            phone = contact.get("phone_number")
                            if phone:
                                self.suffix_trie.delete(phone, contact.get("id"))
                        except Exception:
                            pass
                elif op == "edit":
                    cid = data.get("id")
                    contact = None
                    if cid is not None:
                        contact = next((c for c in self.contacts if c.get("id") == cid), None)
                    else:
                        name = data.get("name")
                        contact = next((c for c in self.contacts if c.get("name") == name), None)
                    if contact:
                        new_name = data.get("new_name")
                        new_phone = data.get("new_phone")
                        new_remark = data.get("new_remark")
                        old_name = contact.get("name")
                        old_phone = contact.get("phone_number")
                        if new_name and new_name != old_name:
                            try:
                                self.trie.delete(old_name, contact.get("id"))
                            except Exception:
                                pass
                            try:
                                self.trie.insert(new_name, contact.get("id"))
                            except Exception:
                                pass
                            contact["name"] = new_name
                        if new_phone and new_phone != old_phone:
                            try:
                                if old_phone:
                                    self.suffix_trie.delete(old_phone, contact.get("id"))
                            except Exception:
                                pass
                            try:
                                self.suffix_trie.insert(new_phone, contact.get("id"))
                            except Exception:
                                pass
                            contact["phone_number"] = new_phone
                        if new_remark is not None:
                            contact["remark"] = new_remark
            except Exception:
                continue

        # 重放完成后，保存一次快照并清空 WAL
        try:
            self._persist_state()
        except Exception:
            pass


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
        choice = input("请选择操作选项：")

        if choice == "1":
            name = input("请输入联系人姓名：")
            phone_number = input("请输入联系人电话：")
            remark = input("请输入备注（可选,不输入默认空白）：")
            cl.add_contact(name,phone_number,remark)
        
        elif choice == "2":
            print("查找方式：1. 按全名  2. 按姓名前缀  3. 按手机号后缀")
            mode = input("请选择查找方式(1/2/3)：").strip()
            if mode == "1":
                name = input("请输入要查找的联系人姓名：")
                contact = cl.search_contact(name)
                if contact:
                    print(f"找到联系人：名称: {contact.get('name')}, 电话: {contact.get('phone_number')}, 备注: {contact.get('remark')}")
                else:
                    print("该联系人不存在")
            elif mode == "2":
                prefix = input("请输入姓名前缀：")
                results = cl.search_by_prefix(prefix)
                if not results:
                    print("未找到匹配的联系人。")
                else:
                    for i, c in enumerate(results, start=1):
                        print(f"{i}. 名称: {c.get('name')}, 电话: {c.get('phone_number')}, 备注: {c.get('remark')}")
            elif mode == "3":
                suffix = input("请输入手机号后缀（例如尾号）：")
                results = cl.search_by_phone_suffix(suffix)
                if not results:
                    print("未找到匹配的联系人。")
                else:
                    for i, c in enumerate(results, start=1):
                        print(f"{i}. 名称: {c.get('name')}, 电话: {c.get('phone_number')}, 备注: {c.get('remark')}")
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
                print(f"当前信息：名称: {contact.get('name')}, 电话: {contact.get('phone_number')}, 备注: {contact.get('remark')}")
                new_name = input("请输入新的姓名（回车保留不变）：").strip()
                new_phone = input("请输入新的电话（回车保留不变）：").strip()
                new_remark = input("请输入新的备注（回车保留不变）：").strip()
                if new_name == "":
                    new_name = None
                if new_phone == "":
                    new_phone = None
                if new_remark == "":
                    new_remark = None
                cl.edit_contact(name, new_name, new_phone, new_remark)
            
        elif choice == "5":
            cl.list_contacts()

        elif choice == "6":
            print("再见！")


        else:
            print("输入错误，请重新输入。")
            
