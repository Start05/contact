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
            

               

