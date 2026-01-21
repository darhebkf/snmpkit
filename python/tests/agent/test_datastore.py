"""Unit Tests for the DataStore class."""

import pytest
from snmpkit.agent.handlers import DataStore
from snmpkit.core import Oid, Value, VarBind


def vb(oid_str: str, value: int = 0) -> VarBind:
    """Helper to create VarBind with Integer value."""
    return VarBind(Oid(oid_str), Value.Integer(value))


@pytest.fixture
def store():
    """Create a fresh DataStore."""
    return DataStore()


class TestDataStoreBasic:
    """Basic DataStore functionality tests."""

    def test_initial_state(self, store):
        """DataStore starts empty."""
        assert store.get("1.3.6.1", None) is None

    def test_init_context(self, store):
        """init_context creates empty context."""
        store.init_context("mycontext")
        assert "mycontext" in store._data
        assert store._data["mycontext"] == {}

    def test_init_context_default(self, store):
        """init_context with None uses empty string key."""
        store.init_context(None)
        assert "" in store._data


class TestDataStoreUpdate:
    """Tests for update method."""

    def test_update_single(self, store):
        """Update stores a single varbind."""
        varbinds = [vb("1.3.6.1.2.1.1.1.0", 42)]
        store.update("1.3.6.1.2.1.1", None, varbinds)

        result = store.get("1.3.6.1.2.1.1.1.0", None)
        assert result is not None
        assert result.value == Value.Integer(42)

    def test_update_multiple(self, store):
        """Update stores multiple varbinds."""
        varbinds = [
            vb("1.3.6.1.2.1.1.1.0", 1),
            vb("1.3.6.1.2.1.1.2.0", 2),
            vb("1.3.6.1.2.1.1.3.0", 3),
        ]
        store.update("1.3.6.1.2.1.1", None, varbinds)

        assert store.get("1.3.6.1.2.1.1.1.0", None) is not None
        assert store.get("1.3.6.1.2.1.1.2.0", None) is not None
        assert store.get("1.3.6.1.2.1.1.3.0", None) is not None

    def test_update_replaces_subtree(self, store):
        """Update replaces existing values under OID prefix."""
        # First update
        store.update("1.3.6.1.2.1.1", None, [vb("1.3.6.1.2.1.1.1.0", 1)])
        assert store.get("1.3.6.1.2.1.1.1.0", None) is not None

        # Second update with different values
        store.update("1.3.6.1.2.1.1", None, [vb("1.3.6.1.2.1.1.2.0", 2)])

        # Old value should be removed
        assert store.get("1.3.6.1.2.1.1.1.0", None) is None
        # New value should exist
        assert store.get("1.3.6.1.2.1.1.2.0", None) is not None

    def test_update_with_context(self, store):
        """Update stores in specified context."""
        store.update("1.3.6.1", "ctx1", [vb("1.3.6.1.1.0", 1)])
        store.update("1.3.6.1", "ctx2", [vb("1.3.6.1.1.0", 2)])

        # Different contexts have different values
        v1 = store.get("1.3.6.1.1.0", "ctx1")
        v2 = store.get("1.3.6.1.1.0", "ctx2")

        assert v1.value == Value.Integer(1)
        assert v2.value == Value.Integer(2)


class TestDataStoreGet:
    """Tests for get method."""

    def test_get_exact_match(self, store):
        """get returns exact OID match."""
        store.update("1.3.6.1", None, [vb("1.3.6.1.1.0", 42)])

        result = store.get("1.3.6.1.1.0", None)
        assert result.value == Value.Integer(42)

    def test_get_missing(self, store):
        """get returns None for missing OID."""
        store.update("1.3.6.1", None, [vb("1.3.6.1.1.0", 42)])

        assert store.get("1.3.6.1.2.0", None) is None

    def test_get_wrong_context(self, store):
        """get returns None for wrong context."""
        store.update("1.3.6.1", "ctx1", [vb("1.3.6.1.1.0", 42)])

        assert store.get("1.3.6.1.1.0", "ctx2") is None


class TestDataStoreGetNext:
    """Tests for get_next method (SNMP GETNEXT)."""

    def test_get_next_basic(self, store):
        """get_next returns next OID in order."""
        store.update(
            "1.3.6.1",
            None,
            [
                vb("1.3.6.1.1.0", 1),
                vb("1.3.6.1.2.0", 2),
                vb("1.3.6.1.3.0", 3),
            ],
        )

        next_oid = store.get_next("1.3.6.1.1.0", "", None)
        assert next_oid == "1.3.6.1.2.0"

    def test_get_next_lexicographic_order(self, store):
        """get_next follows lexicographic order (1.10 > 1.2)."""
        store.update(
            "1.3.6.1",
            None,
            [
                vb("1.3.6.1.1", 1),
                vb("1.3.6.1.2", 2),
                vb("1.3.6.1.10", 10),
            ],
        )

        # After 1.3.6.1.2 should be 1.3.6.1.10
        next_oid = store.get_next("1.3.6.1.2", "", None)
        assert next_oid == "1.3.6.1.10"

    def test_get_next_nonexistent_oid(self, store):
        """get_next finds next after non-existent OID."""
        store.update(
            "1.3.6.1",
            None,
            [
                vb("1.3.6.1.1.0", 1),
                vb("1.3.6.1.3.0", 3),
            ],
        )

        # Query for 1.3.6.1.2.0 which doesn't exist
        next_oid = store.get_next("1.3.6.1.2.0", "", None)
        assert next_oid == "1.3.6.1.3.0"

    def test_get_next_respects_end_oid(self, store):
        """get_next stops at end_oid boundary."""
        store.update(
            "1.3.6.1",
            None,
            [
                vb("1.3.6.1.1.0", 1),
                vb("1.3.6.1.2.0", 2),
                vb("1.3.6.1.3.0", 3),
            ],
        )

        # End at 1.3.6.1.2.0
        next_oid = store.get_next("1.3.6.1.1.0", "1.3.6.1.2.0", None)
        assert next_oid == "1.3.6.1.2.0"

        # Should not go past end
        next_oid = store.get_next("1.3.6.1.2.0", "1.3.6.1.2.0", None)
        assert next_oid is None

    def test_get_next_empty_store(self, store):
        """get_next returns None for empty store."""
        store.init_context(None)
        assert store.get_next("1.3.6.1", "", None) is None

    def test_get_next_past_last(self, store):
        """get_next returns None past last OID."""
        store.update("1.3.6.1", None, [vb("1.3.6.1.1.0", 1)])

        assert store.get_next("1.3.6.1.1.0", "", None) is None

    def test_get_next_with_context(self, store):
        """get_next respects context."""
        store.update(
            "1.3.6.1",
            "ctx1",
            [
                vb("1.3.6.1.1.0", 1),
                vb("1.3.6.1.2.0", 2),
            ],
        )
        store.update(
            "1.3.6.1",
            "ctx2",
            [
                vb("1.3.6.1.1.0", 10),
                vb("1.3.6.1.3.0", 30),
            ],
        )

        # In ctx1, after 1.0 is 2.0
        assert store.get_next("1.3.6.1.1.0", "", "ctx1") == "1.3.6.1.2.0"
        # In ctx2, after 1.0 is 3.0
        assert store.get_next("1.3.6.1.1.0", "", "ctx2") == "1.3.6.1.3.0"


class TestDataStoreLexicographicOrdering:
    """Tests for correct SNMP lexicographic OID ordering."""

    def test_numeric_vs_string_order(self, store):
        """OIDs are compared numerically, not as strings."""
        store.update(
            "1.3.6.1",
            None,
            [
                vb("1.3.6.1.1", 1),
                vb("1.3.6.1.2", 2),
                vb("1.3.6.1.10", 10),
                vb("1.3.6.1.20", 20),
            ],
        )

        # Walk through all OIDs
        oid = store.get_next("1.3.6.1.0", "", None)
        assert oid == "1.3.6.1.1"

        oid = store.get_next("1.3.6.1.1", "", None)
        assert oid == "1.3.6.1.2"

        oid = store.get_next("1.3.6.1.2", "", None)
        assert oid == "1.3.6.1.10"  # NOT 1.3.6.1.20

        oid = store.get_next("1.3.6.1.10", "", None)
        assert oid == "1.3.6.1.20"

    def test_shorter_oid_comes_first(self, store):
        """Shorter OID comes before longer OID with same prefix."""
        store.update(
            "1.3.6.1",
            None,
            [
                vb("1.3.6.1.1", 1),
                vb("1.3.6.1.1.1", 11),
                vb("1.3.6.1.1.2", 12),
            ],
        )

        oid = store.get_next("1.3.6.1.0", "", None)
        assert oid == "1.3.6.1.1"

        oid = store.get_next("1.3.6.1.1", "", None)
        assert oid == "1.3.6.1.1.1"

    def test_table_walk_simulation(self, store):
        """Simulate walking an SNMP table."""
        # Table with 3 rows, 2 columns
        store.update(
            "1.3.6.1",
            None,
            [
                vb("1.3.6.1.1.1.1", 11),  # col1, row1
                vb("1.3.6.1.1.1.2", 12),  # col1, row2
                vb("1.3.6.1.1.1.3", 13),  # col1, row3
                vb("1.3.6.1.1.2.1", 21),  # col2, row1
                vb("1.3.6.1.1.2.2", 22),  # col2, row2
                vb("1.3.6.1.1.2.3", 23),  # col2, row3
            ],
        )

        # Walk column 1
        expected = ["1.3.6.1.1.1.1", "1.3.6.1.1.1.2", "1.3.6.1.1.1.3"]
        oid = store.get_next("1.3.6.1.1.1.0", "", None)
        for exp in expected:
            assert oid == exp
            oid = store.get_next(oid, "", None)


class TestDataStoreOidLe:
    """Tests for _oid_le helper method."""

    def test_oid_le_equal(self, store):
        """Equal OIDs are <=."""
        assert store._oid_le("1.3.6.1", "1.3.6.1") is True

    def test_oid_le_less(self, store):
        """Smaller OID is <=."""
        assert store._oid_le("1.3.6.1", "1.3.6.2") is True

    def test_oid_le_greater(self, store):
        """Greater OID is not <=."""
        assert store._oid_le("1.3.6.2", "1.3.6.1") is False

    def test_oid_le_empty_end(self, store):
        """Empty end OID means no upper bound."""
        assert store._oid_le("1.3.6.1.9999", "") is True
