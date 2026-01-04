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
