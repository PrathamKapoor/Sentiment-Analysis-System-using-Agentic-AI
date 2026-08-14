from .base import SourceAdapter


class MockForumAdapter(SourceAdapter):
    def __init__(self, records=None):
        self.records, self.calls = records or [], 0

    def search(self, source, intent):
        self.calls += 1
        return list(self.records)
