class ContactList:
    def __init__(self):
        self.contacts = []

#添加联系人
    def add_contact(self, name, phone_number, remark=""):
        self.contacts.append({
            "name": name,
            "phone_number": phone_number,
            "remark": remark,
        })
        print(f"联系人 {name} 添加成功！")

#查找联系人(姓名)
    def search_contact(self, name):
        for c in self.contacts:
            if c.get("name") == name:
                return c
        return None

#删除联系人
    def delete_contact(self, name):
        contact = self.search_contact(name)
        if contact:
            self.contacts.remove(contact)
            print(f"联系人 {name} 删除成功！")
            return True
        else:
            print(f"不存在 {name}，删除失败")
            return False

#修改联系人信息
    def edit_contact(self, name, new_name=None, new_phone=None, new_remark=None):
        contact = self.search_contact(name)
        if not contact:
            print(f"未找到联系人：{name}")
            return False

        if new_name is not None:
            contact["name"] = new_name
        if new_phone is not None:
            contact["phone_number"] = new_phone
        if new_remark is not None:
            contact["remark"] = new_remark

        print(f"联系人 {name} 已更新。")
        return True

#列出所有联系人
    def list_contacts(self):
        if not self.contacts:
            print("联系人列表为空。")
            return
        for i, c in enumerate(self.contacts, start=1):
            print(f"{i}. 名称: {c.get('name')}, 电话: {c.get('phone_number')}, 备注: {c.get('remark')}")


