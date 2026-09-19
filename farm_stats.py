"""Persist confirmed gross battle earnings independently of village spending."""
import json
import uuid
from pathlib import Path


class FarmStats:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"gold": 0, "elixir": 0, "dark_elixir": 0, "battles": 0, "pending": None}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Fichier de statistiques invalide")
            for key in ("gold", "elixir", "dark_elixir", "battles"):
                if type(data.get(key)) is not int or data[key] < 0:
                    raise ValueError("Fichier de statistiques invalide")
            pending = data.get("pending")
            if pending is not None and (not isinstance(pending, dict) or
                    not isinstance(pending.get("window_title"), str) or
                    not isinstance(pending.get("id"), str)):
                raise ValueError("Combat en attente invalide dans les statistiques")
            self.data = data

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
        self.data = data

    def begin(self, window_title):
        if self.data.get("pending"):
            raise RuntimeError("Le résultat précédent doit être traité avant une nouvelle attaque")
        self._save({**self.data, "pending": {"id": uuid.uuid4().hex, "window_title": window_title}})

    def finish(self, amounts):
        if not self.data.get("pending"):
            return False
        if len(amounts) != 3 or any(type(v) is not int or v < 0 for v in amounts):
            raise ValueError("Butin invalide")
        data = {**self.data, "pending": None, "battles": self.data["battles"] + 1}
        for key, value in zip(("gold", "elixir", "dark_elixir"), amounts):
            data[key] += value
        self._save(data)
        return True

    def clear_pending(self):
        if self.data.get("pending"):
            self._save({**self.data, "pending": None})

    def defer_result(self, image):
        """Archive an unreadable result before releasing the next battle."""
        pending = self.data.get('pending')
        if not pending:
            return None
        directory = self.path.parent / 'unread-results'
        directory.mkdir(parents=True, exist_ok=True)
        # Use a fresh filename, never a path supplied by persisted metadata.
        stem = directory / uuid.uuid4().hex
        screenshot = stem.with_suffix('.png')
        image.save(screenshot)
        stem.with_suffix('.json').write_text(json.dumps(pending, ensure_ascii=False), encoding='utf-8')
        self.clear_pending()
        return screenshot
