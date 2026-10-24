import csv
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Optional, Set
from code.config import USER_IDENTITIES_PATH, USER_AUDIT_LOG_PATH

@dataclass
class UserIdentity:
    user_id: str
    current_name: str
    names: Set[str] = field(default_factory=set)
    current_email: str = ""
    emails: Set[str] = field(default_factory=set)
    current_phone: str = ""
    phones: Set[str] = field(default_factory=set)
    email_hashes: Set[str] = field(default_factory=set)

class IdentityResolver:
    def __init__(self, identities_path=USER_IDENTITIES_PATH, audit_log_path=USER_AUDIT_LOG_PATH):
        self.identities_path = identities_path
        self.audit_log_path = audit_log_path
        self.users: Dict[str, UserIdentity] = {}
        self.email_to_uid: Dict[str, str] = {}
        self._load()

    def _load(self):
        # 1. Load current identities snapshot
        with open(self.identities_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"].strip()
                name = row["name"].strip()
                email = row["email"].strip().lower()
                phone = row["phone"].strip()
                email_hash = row["email_hash"].strip().lower()

                user = UserIdentity(
                    user_id=uid,
                    current_name=name,
                    current_email=email,
                    current_phone=phone,
                )
                user.names.add(name)
                user.emails.add(email)
                user.phones.add(phone)
                user.email_hashes.add(email_hash)
                # Also add programmatic sha256
                user.email_hashes.add(hashlib.sha256(email.encode("utf-8")).hexdigest().lower())

                self.users[uid] = user
                self.email_to_uid[email] = uid

        # 2. Enrich with historical mutations from user audit log
        with open(self.audit_log_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                uid = row["user_id"].strip()
                if uid not in self.users:
                    continue
                user = self.users[uid]
                field_name = row["field_name"].strip()
                old_val = row["old_value"].strip()
                new_val = row["new_value"].strip()

                if field_name == "email":
                    for em in (old_val, new_val):
                        if em:
                            em_clean = em.lower()
                            user.emails.add(em_clean)
                            self.email_to_uid[em_clean] = uid
                            user.email_hashes.add(hashlib.sha256(em_clean.encode("utf-8")).hexdigest().lower())
                elif field_name == "email_hash":
                    for h in (old_val, new_val):
                        if h:
                            user.email_hashes.add(h.strip().lower())
                elif field_name == "phone":
                    if old_val:
                        user.phones.add(old_val)
                    if new_val:
                        user.phones.add(new_val)
                elif field_name == "name":
                    if old_val:
                        user.names.add(old_val)
                    if new_val:
                        user.names.add(new_val)

    def resolve_by_email(self, email: str) -> Optional[UserIdentity]:
        clean_email = email.strip().lower()
        uid = self.email_to_uid.get(clean_email)
        if uid:
            return self.users.get(uid)
        return None

    def get_by_user_id(self, user_id: str) -> Optional[UserIdentity]:
        return self.users.get(user_id.strip())
