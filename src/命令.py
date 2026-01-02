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
            

               

