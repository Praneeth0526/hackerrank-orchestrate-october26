import re

NON_DELETION_PATTERNS = [
    r"leave (the|my) (account|profile|records|purchase history)",
    r"leave .* active",
    r"leave .* in place",
    r"keep the account",
    r"keep .* as it is",
    r"do not (close|delete|erase)",
    r"don't (delete|close|erase|change)",
    r"without removing",
    r"marketing lists? only",
    r"promotional emails?",
    r"not (asking for|a request for|a request to) (deletion|erase|delete|erasure)",
    r"portable format",
    r"what personal information you hold",
    r"information request",
    r"copy of (last year\'s|the information held|my account)",
    r"help resetting the login",
    r"surname is misspelled",
    r"replace it with the new",
    r"continue using the service",
]

DELETION_PATTERNS = [
    # English with comprehensive suffixes
    r"\b(delet(e|ed|ing|ion|ions)?|eras(e|ed|ing|ure|ures)?|clos(e|ed|ing|ure)?|remov(e|ed|al|als|ing)?|clean(ed|ing)?|purg(e|ed|ing)?)\b",
    r"\bgone\b",
    # French
    r"\b(suppress|suppression|supprimer|effacer|fermer)\b",
    # Spanish
    r"\b(eliminar|eliminación|borrar|cancelar)\b",
    # Portuguese
    r"\b(exclusão|excluir|apagar|eliminar)\b",
    # German
    r"\b(löschen|löschung|schließen|entfernen)\b",
    # Japanese / Korean
    r"(削除|消去|삭제)",
]

class IntentClassifier:
    """
    Classifies user request_text to determine whether deletion is authorized.
    Returns True if deletion is requested, False if NOT_APPLICABLE.
    """
    def __init__(self):
        self.non_deletion_regexes = [re.compile(pat, re.IGNORECASE) for pat in NON_DELETION_PATTERNS]
        self.deletion_regexes = [re.compile(pat, re.IGNORECASE) for pat in DELETION_PATTERNS]

    def is_deletion_authorized(self, text: str) -> bool:
        if not text:
            return False
        clean_text = text.strip()

        # 1. First check explicit non-deletion / retention / opt-out cues
        for reg in self.non_deletion_regexes:
            if reg.search(clean_text):
                return False

        # 2. Check for affirmative deletion keywords across languages
        for reg in self.deletion_regexes:
            if reg.search(clean_text):
                return True

        return False
