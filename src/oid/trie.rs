//! OID Trie - A radix trie optimized for SNMP OID lookups.
//!
//! Provides O(k) lookup where k is the OID depth, with efficient
//! `get_next` for SNMP GETNEXT operations.

use std::collections::BTreeMap;

use super::Oid;

#[derive(Debug, Clone)]
struct TrieNode<V> {
    value: Option<V>,
    children: BTreeMap<u32, TrieNode<V>>,
}

impl<V> Default for TrieNode<V> {
    fn default() -> Self {
        Self {
            value: None,
            children: BTreeMap::new(),
        }
    }
}

/// A trie (prefix tree) for OID-keyed data.
///
/// Optimized for SNMP operations:
/// - O(k) exact lookups where k is OID depth
/// - O(k) longest prefix matching for registration lookups
/// - O(k + m) get_next for GETNEXT where m is nodes traversed
///
/// Uses `BTreeMap` for children to maintain lexicographic ordering,
/// which is essential for correct SNMP GETNEXT behavior.
#[derive(Debug, Clone)]
pub struct OidTrie<V> {
    root: TrieNode<V>,
    len: usize,
}

impl<V> Default for OidTrie<V> {
    fn default() -> Self {
        Self::new()
    }
}

impl<V> OidTrie<V> {
    /// Creates an empty trie.
    pub fn new() -> Self {
        Self {
            root: TrieNode::default(),
            len: 0,
        }
    }

    /// Returns the number of entries in the trie.
    pub fn len(&self) -> usize {
        self.len
    }

    /// Returns `true` if the trie contains no entries.
    pub fn is_empty(&self) -> bool {
        self.len == 0
    }

    /// Removes all entries from the trie.
    pub fn clear(&mut self) {
        self.root = TrieNode::default();
        self.len = 0;
    }

    /// Inserts a value at the given OID.
    ///
    /// Returns the previous value if the OID was already present.
    pub fn insert(&mut self, oid: &Oid, value: V) -> Option<V> {
        let mut node = &mut self.root;

        for &part in oid.parts() {
            node = node.children.entry(part).or_default();
        }

        let old = node.value.replace(value);
        if old.is_none() {
            self.len += 1;
        }
        old
    }

    /// Returns a reference to the value at the given OID.
    pub fn get(&self, oid: &Oid) -> Option<&V> {
        let mut node = &self.root;

        for &part in oid.parts() {
            node = node.children.get(&part)?;
        }

        node.value.as_ref()
    }

    /// Returns a mutable reference to the value at the given OID.
    pub fn get_mut(&mut self, oid: &Oid) -> Option<&mut V> {
        let mut node = &mut self.root;

        for &part in oid.parts() {
            node = node.children.get_mut(&part)?;
        }

        node.value.as_mut()
    }

    /// Returns `true` if the trie contains the given OID.
    pub fn contains(&self, oid: &Oid) -> bool {
        self.get(oid).is_some()
    }

    /// Removes and returns the value at the given OID.
    ///
    /// Also prunes empty ancestor nodes to prevent memory leaks.
    pub fn remove(&mut self, oid: &Oid) -> Option<V> {
        let parts = oid.parts();
        let removed = Self::remove_recursive(&mut self.root, parts, 0);
        if removed.is_some() {
            self.len -= 1;
        }
        removed
    }

    fn remove_recursive(node: &mut TrieNode<V>, parts: &[u32], depth: usize) -> Option<V> {
        if depth == parts.len() {
            return node.value.take();
        }

        let part = parts[depth];

        if let Some(child) = node.children.get_mut(&part) {
            let value = Self::remove_recursive(child, parts, depth + 1);

            if child.value.is_none() && child.children.is_empty() {
                node.children.remove(&part);
            }

            value
        } else {
            None
        }
    }

    /// Finds the longest OID prefix that has a value.
    ///
    /// Used for finding which registration handles a given OID.
    /// Returns the matching OID and its value.
    pub fn longest_prefix(&self, oid: &Oid) -> Option<(Oid, &V)> {
        let mut node = &self.root;
        let mut last_match: Option<(usize, &V)> = None;
        let parts = oid.parts();
        let mut matched_depth = 0;

        for &part in parts {
            if let Some(ref v) = node.value {
                last_match = Some((matched_depth, v));
            }

            match node.children.get(&part) {
                Some(child) => {
                    node = child;
                    matched_depth += 1;
                }
                None => break,
            }
        }

        // Check if final node has a value
        if let Some(ref v) = node.value {
            last_match = Some((matched_depth, v));
        }

        last_match.map(|(depth, v)| {
            let matched_parts = &parts[..depth];
            (Oid::new(matched_parts.to_vec()).unwrap(), v)
        })
    }

    /// Finds the next OID after the given one in lexicographic order.
    ///
    /// This is the core operation for SNMP GETNEXT. The algorithm:
    /// 1. Navigate to the target OID's position in the trie
    /// 2. If we're at the exact OID, look for children or siblings
    /// 3. If we're past the target, find the first value in current subtree
    /// 4. Use BTreeMap's ordering to find the next sibling when needed
    pub fn get_next(&self, oid: &Oid) -> Option<(Oid, &V)> {
        let mut path = Vec::with_capacity(oid.parts().len() + 4);
        let result = Self::find_next(&self.root, &mut path, oid.parts(), 0);
        result.map(|(parts, v)| (Oid::new(parts).unwrap(), v))
    }

    /// Recursive helper for get_next.
    ///
    /// Returns the path to the next value and a reference to it.
    fn find_next<'a>(
        node: &'a TrieNode<V>,
        path: &mut Vec<u32>,
        target: &[u32],
        depth: usize,
    ) -> Option<(Vec<u32>, &'a V)> {
        if depth < target.len() {
            // Still navigating toward target - need to go deeper or find sibling
            let target_part = target[depth];

            // Look at children >= target_part
            for (&part, child) in node.children.range(target_part..) {
                path.push(part);

                let result = if part == target_part {
                    // Exact match - continue deeper
                    Self::find_next(child, path, target, depth + 1)
                } else {
                    // Found a sibling > target - return first value in its subtree
                    Self::first_in_subtree(child, path)
                };

                if result.is_some() {
                    return result;
                }
                path.pop();
            }
            None
        } else if depth == target.len() {
            // At exact target depth - look for children (deeper OIDs)
            for (&part, child) in &node.children {
                path.push(part);
                if let Some(result) = Self::first_in_subtree(child, path) {
                    return Some(result);
                }
                path.pop();
            }
            None
        } else {
            // Past target (target is prefix of current path) - return this node if it has value
            if let Some(ref v) = node.value {
                return Some((path.clone(), v));
            }

            // Otherwise find first value in any child
            for (&part, child) in &node.children {
                path.push(part);
                if let Some(result) = Self::first_in_subtree(child, path) {
                    return Some(result);
                }
                path.pop();
            }
            None
        }
    }

    /// Finds the first value in a subtree (depth-first, lexicographic order).
    fn first_in_subtree<'a>(
        node: &'a TrieNode<V>,
        path: &mut Vec<u32>,
    ) -> Option<(Vec<u32>, &'a V)> {
        if let Some(ref v) = node.value {
            return Some((path.clone(), v));
        }

        for (&part, child) in &node.children {
            path.push(part);
            if let Some(result) = Self::first_in_subtree(child, path) {
                return Some(result);
            }
            path.pop();
        }
        None
    }

    /// Returns an iterator over all (OID, value) pairs in lexicographic order.
    pub fn iter(&self) -> TrieIter<'_, V> {
        TrieIter::new(&self.root)
    }

    /// Returns an iterator over all OIDs in lexicographic order.
    pub fn keys(&self) -> impl Iterator<Item = Oid> + '_ {
        self.iter().map(|(oid, _)| oid)
    }

    /// Returns an iterator over all values in lexicographic OID order.
    pub fn values(&self) -> impl Iterator<Item = &V> {
        self.iter().map(|(_, v)| v)
    }
}

/// Iterator over trie entries in lexicographic OID order.
pub struct TrieIter<'a, V> {
    // Stack of (node, children iterator)
    #[allow(clippy::type_complexity)]
    stack: Vec<(
        &'a TrieNode<V>,
        std::collections::btree_map::Iter<'a, u32, TrieNode<V>>,
    )>,
    path: Vec<u32>,
    // Pending value from current node (before descending into children)
    pending: Option<&'a V>,
}

impl<'a, V> TrieIter<'a, V> {
    fn new(root: &'a TrieNode<V>) -> Self {
        let mut iter = Self {
            stack: Vec::new(),
            path: Vec::new(),
            pending: root.value.as_ref(),
        };
        iter.stack.push((root, root.children.iter()));
        iter
    }
}

impl<'a, V> Iterator for TrieIter<'a, V> {
    type Item = (Oid, &'a V);

    fn next(&mut self) -> Option<Self::Item> {
        // Return pending value first (current node's value)
        if let Some(v) = self.pending.take() {
            return Some((Oid::new(self.path.clone()).unwrap(), v));
        }

        // Depth-first traversal
        while let Some((_, children_iter)) = self.stack.last_mut() {
            if let Some((&part, child)) = children_iter.next() {
                self.path.push(part);
                self.stack.push((child, child.children.iter()));

                if let Some(ref v) = child.value {
                    return Some((Oid::new(self.path.clone()).unwrap(), v));
                }
            } else {
                // No more children at this level, go back up
                self.stack.pop();
                self.path.pop();
            }
        }

        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_insert_get() {
        let mut trie = OidTrie::new();
        let oid: Oid = "1.3.6.1.4".parse().unwrap();

        trie.insert(&oid, "test");
        assert_eq!(trie.get(&oid), Some(&"test"));
        assert_eq!(trie.len(), 1);
    }

    #[test]
    fn test_insert_replace() {
        let mut trie = OidTrie::new();
        let oid: Oid = "1.3.6.1".parse().unwrap();

        assert_eq!(trie.insert(&oid, "first"), None);
        assert_eq!(trie.insert(&oid, "second"), Some("first"));
        assert_eq!(trie.get(&oid), Some(&"second"));
        assert_eq!(trie.len(), 1);
    }

    #[test]
    fn test_remove() {
        let mut trie = OidTrie::new();
        let oid: Oid = "1.3.6.1".parse().unwrap();

        trie.insert(&oid, "test");
        assert_eq!(trie.remove(&oid), Some("test"));
        assert_eq!(trie.get(&oid), None);
        assert_eq!(trie.len(), 0);
    }

    #[test]
    fn test_clear() {
        let mut trie = OidTrie::new();
        trie.insert(&"1.3.6.1".parse().unwrap(), "a");
        trie.insert(&"1.3.6.2".parse().unwrap(), "b");
        trie.insert(&"1.3.6.3".parse().unwrap(), "c");

        assert_eq!(trie.len(), 3);
        trie.clear();
        assert_eq!(trie.len(), 0);
        assert!(trie.is_empty());
        assert_eq!(trie.get(&"1.3.6.1".parse().unwrap()), None);
    }

    #[test]
    fn test_longest_prefix() {
        let mut trie = OidTrie::new();
        let oid1: Oid = "1.3.6".parse().unwrap();
        let oid2: Oid = "1.3.6.1.4".parse().unwrap();

        trie.insert(&oid1, "short");
        trie.insert(&oid2, "long");

        let query: Oid = "1.3.6.1.4.1.12345".parse().unwrap();
        let (prefix, value) = trie.longest_prefix(&query).unwrap();

        assert_eq!(prefix.to_string(), "1.3.6.1.4");
        assert_eq!(*value, "long");
    }

    #[test]
    fn test_get_next() {
        let mut trie = OidTrie::new();

        let oid1: Oid = "1.3.6.1.1".parse().unwrap();
        let oid2: Oid = "1.3.6.1.2".parse().unwrap();
        let oid3: Oid = "1.3.6.1.3".parse().unwrap();

        trie.insert(&oid1, "first");
        trie.insert(&oid2, "second");
        trie.insert(&oid3, "third");

        let (next, value) = trie.get_next(&oid1).unwrap();
        assert_eq!(next.to_string(), "1.3.6.1.2");
        assert_eq!(*value, "second");

        let (next, value) = trie.get_next(&oid2).unwrap();
        assert_eq!(next.to_string(), "1.3.6.1.3");
        assert_eq!(*value, "third");
    }

    #[test]
    fn test_get_next_subtree() {
        let mut trie = OidTrie::new();

        let oid1: Oid = "1.3.6.1".parse().unwrap();
        let oid2: Oid = "1.3.6.1.1".parse().unwrap();

        trie.insert(&oid1, "parent");
        trie.insert(&oid2, "child");

        let (next, value) = trie.get_next(&oid1).unwrap();
        assert_eq!(next.to_string(), "1.3.6.1.1");
        assert_eq!(*value, "child");
    }

    #[test]
    fn test_get_next_empty_trie() {
        let trie: OidTrie<&str> = OidTrie::new();
        let oid: Oid = "1.3.6.1".parse().unwrap();
        assert!(trie.get_next(&oid).is_none());
    }

    #[test]
    fn test_get_next_last_element() {
        let mut trie = OidTrie::new();
        let oid: Oid = "1.3.6.1".parse().unwrap();
        trie.insert(&oid, "only");

        // get_next on the only element should return None
        assert!(trie.get_next(&oid).is_none());
    }

    #[test]
    fn test_get_next_nonexistent_oid() {
        let mut trie = OidTrie::new();
        trie.insert(&"1.3.6.1.1".parse().unwrap(), "a");
        trie.insert(&"1.3.6.1.3".parse().unwrap(), "c");

        // Query for 1.3.6.1.2 which doesn't exist - should return 1.3.6.1.3
        let query: Oid = "1.3.6.1.2".parse().unwrap();
        let (next, value) = trie.get_next(&query).unwrap();
        assert_eq!(next.to_string(), "1.3.6.1.3");
        assert_eq!(*value, "c");
    }

    #[test]
    fn test_get_next_prefix_query() {
        let mut trie = OidTrie::new();
        trie.insert(&"1.3.6.1.1.1".parse().unwrap(), "deep");
        trie.insert(&"1.3.6.1.2".parse().unwrap(), "sibling");

        // Query for prefix - should return first child
        let query: Oid = "1.3.6.1.1".parse().unwrap();
        let (next, value) = trie.get_next(&query).unwrap();
        assert_eq!(next.to_string(), "1.3.6.1.1.1");
        assert_eq!(*value, "deep");
    }

    #[test]
    fn test_iter() {
        let mut trie = OidTrie::new();
        trie.insert(&"1.3.6.1".parse().unwrap(), "a");
        trie.insert(&"1.3.6.2".parse().unwrap(), "b");
        trie.insert(&"1.3.6.1.1".parse().unwrap(), "c");

        let items: Vec<_> = trie.iter().collect();
        assert_eq!(items.len(), 3);

        // Should be in lexicographic order
        assert_eq!(items[0].0.to_string(), "1.3.6.1");
        assert_eq!(items[1].0.to_string(), "1.3.6.1.1");
        assert_eq!(items[2].0.to_string(), "1.3.6.2");
    }

    #[test]
    fn test_keys_values() {
        let mut trie = OidTrie::new();
        trie.insert(&"1.3.6.1".parse().unwrap(), "a");
        trie.insert(&"1.3.6.2".parse().unwrap(), "b");

        let keys: Vec<_> = trie.keys().collect();
        assert_eq!(keys.len(), 2);
        assert_eq!(keys[0].to_string(), "1.3.6.1");
        assert_eq!(keys[1].to_string(), "1.3.6.2");

        let values: Vec<_> = trie.values().collect();
        assert_eq!(values, vec![&"a", &"b"]);
    }

    #[test]
    fn test_iter_empty() {
        let trie: OidTrie<&str> = OidTrie::new();
        assert_eq!(trie.iter().count(), 0);
    }
}
