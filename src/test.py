class ContactList:
    def __init__(self):
        self.contacts = []
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

        contact_id = contact.get("id")

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


        print(f"联系人 {name} 删除成功！")
        return True

#修改联系人信息
    def edit_contact(self, name, new_name=None, new_phone=None, new_remark=None):
        contact = self.search_contact(name)
        if not contact:
            print(f"未找到联系人：{name}")
            return False

        contact_id = contact.get("id")

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
            name = input("请输入要查找的联系人姓名：")
            contact = cl.search_contact(name)
            if contact:
                print(f"找到联系人：名称: {contact.get('name')}, 电话: {contact.get('phone_number')}, 备注: {contact.get('remark')}")
            else:
                print("该联系人不存在")
        
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
            

               

