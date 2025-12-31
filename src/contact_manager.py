# -*- coding: utf-8 -*-
import os
import json
import tempfile
from typing import Dict, Optional, List
from pathlib import Path
from trie import Trie


class Contact:
    def __init__(self, cid: int, name: str, phone: str, remark: str = ""):
        self.id = cid
        self.name = name
        self.phone = phone
        self.remark = remark

    def to_dict(self):
        return {"id": self.id, "name": self.name, "phone": self.phone, "remark": self.remark}

    @staticmethod
    def from_dict(d):
        return Contact(d["id"], d["name"], d["phone"], d.get("remark", ""))


class ContactManager:
    DATA_DIR = Path(__file__).resolve().parent / "data"
    SNAPSHOT = DATA_DIR / "contacts.json"
    JOURNAL = DATA_DIR / "journal.log"

    def __init__(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.contacts: Dict[int, Contact] = {}
        self.next_id = 1
        self.name_trie = Trie()
        self.phone_trie = Trie()
        self.phone_index: Dict[str, int] = {}
        self._load()

    # ---------- persistence / WAL helpers ----------
    def _append_journal(self, record: dict):
        with open(self.JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _write_snapshot(self):
        tmp = self.SNAPSHOT.with_suffix(".json.tmp")
        payload = {"next_id": self.next_id, "contacts": [c.to_dict() for c in self.contacts.values()]}
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.SNAPSHOT)

    def _clear_journal(self):
        try:
            os.remove(self.JOURNAL)
        except FileNotFoundError:
            pass

    def _load(self):
        # load snapshot
        if self.SNAPSHOT.exists():
            with open(self.SNAPSHOT, "r", encoding="utf-8") as f:
                payload = json.load(f)
                self.next_id = payload.get("next_id", 1)
                for d in payload.get("contacts", []):
                    c = Contact.from_dict(d)
                    self._add_in_memory(c)

        # if journal exists, replay then snapshot and remove journal
        if self.JOURNAL.exists():
            with open(self.JOURNAL, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    rec = json.loads(line)
                    op = rec.get("op")
                    if op == "add":
                        d = rec["contact"]
                        c = Contact(d["id"], d["name"], d["phone"], d.get("remark", ""))
                        self._add_in_memory(c)
                        self.next_id = max(self.next_id, c.id + 1)
                    elif op == "delete":
                        cid = rec["id"]
                        self._delete_in_memory(cid)
                    elif op == "edit":
                        cid = rec["id"]
                        fields = rec["fields"]
                        self._edit_in_memory(cid, **fields)
            # persist a new snapshot and clear journal
            self._write_snapshot()
            self._clear_journal()

    # ---------- in-memory helpers (do not persist) ----------
    def _add_in_memory(self, contact: Contact):
        self.contacts[contact.id] = contact
        # index name and phone
        self.name_trie.insert(contact.name, contact.id)
        self.phone_trie.insert(contact.phone, contact.id)
        self.phone_index[contact.phone] = contact.id

    def _delete_in_memory(self, cid: int):
        c = self.contacts.get(cid)
        if not c:
            return False
        self.name_trie.delete(c.name, cid)
        self.phone_trie.delete(c.phone, cid)
        self.phone_index.pop(c.phone, None)
        del self.contacts[cid]
        return True

    def _edit_in_memory(self, cid: int, **fields):
        c = self.contacts.get(cid)
        if not c:
            return False
        # update indices when changing name/phone
        if "name" in fields and fields["name"] != c.name:
            self.name_trie.delete(c.name, cid)
            c.name = fields["name"]
            self.name_trie.insert(c.name, cid)
        if "phone" in fields and fields["phone"] != c.phone:
            old_phone = c.phone
            self.phone_trie.delete(old_phone, cid)
            self.phone_index.pop(old_phone, None)
            c.phone = fields["phone"]
            self.phone_trie.insert(c.phone, cid)
            self.phone_index[c.phone] = cid
        if "remark" in fields:
            c.remark = fields["remark"]
        return True

    # ---------- public API (atomic operations) ----------
    def add_contact(self, name: str, phone: str, remark: str = "") -> Optional[int]:
        # phone uniqueness enforced
        if phone in self.phone_index:
            return None
        cid = self.next_id
        self.next_id += 1
        contact = Contact(cid, name, phone, remark)
        # write journal
        rec = {"op": "add", "contact": contact.to_dict()}
        self._append_journal(rec)
        # apply in memory
        self._add_in_memory(contact)
        # flush snapshot atomically
        self._write_snapshot()
        # clear journal
        self._clear_journal()
        return cid

    def delete_contact_by_id(self, cid: int) -> bool:
        if cid not in self.contacts:
            return False
        rec = {"op": "delete", "id": cid}
        self._append_journal(rec)
        ok = self._delete_in_memory(cid)
        if ok:
            self._write_snapshot()
            self._clear_journal()
        return ok

    def edit_contact(self, cid: int, **fields) -> bool:
        if cid not in self.contacts:
            return False
        # if phone will change, check uniqueness
        if "phone" in fields and fields["phone"] != self.contacts[cid].phone:
            if fields["phone"] in self.phone_index:
                return False
        rec = {"op": "edit", "id": cid, "fields": fields}
        self._append_journal(rec)
        ok = self._edit_in_memory(cid, **fields)
        if ok:
            self._write_snapshot()
            self._clear_journal()
        return ok

    # ---------- query API ----------
    def list_all(self) -> List[Dict]:
        return [c.to_dict() for c in sorted(self.contacts.values(), key=lambda x: x.id)]

    def search_by_name_exact(self, name: str) -> List[Dict]:
        ids = self.name_trie.search_prefix(name)
        # exact match: filter by exact name
        res = [self.contacts[i].to_dict() for i in ids if self.contacts[i].name == name]
        return res

    def search_by_name_prefix(self, prefix: str) -> List[Dict]:
        ids = self.name_trie.search_prefix(prefix)
        return [self.contacts[i].to_dict() for i in ids]

    def search_by_phone_exact(self, phone: str) -> Optional[Dict]:
        cid = self.phone_index.get(phone)
        if cid:
            return self.contacts[cid].to_dict()
        return None

    def search_by_phone_prefix(self, prefix: str) -> List[Dict]:
        ids = self.phone_trie.search_prefix(prefix)
        return [self.contacts[i].to_dict() for i in ids]
