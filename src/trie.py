# 前缀索引（按联系人姓名），索引使用联系人唯一整数 id
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