from .base import SourceAdapter


class MockPublicApiAdapter(SourceAdapter):
    def __init__(self, records=None):
        self.records = records if records is not None else [{"id": "public-1", "text": "Reliable camera and excellent battery.", "rating": 4.5, "entity": "Samsung Galaxy S25", "url": "https://api.example.test/reviews/1"}]
        self.calls = 0

    def search(self, source, intent):
        self.calls += 1
        return list(self.records)
