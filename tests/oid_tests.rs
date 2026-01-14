use snmpkit::oid::{Oid, OidTrie};

#[test]
fn test_oid_roundtrip() {
    let oid: Oid = "1.3.6.1.4.1.12345".parse().unwrap();
    assert_eq!(oid.to_string(), "1.3.6.1.4.1.12345");
}

#[test]
fn test_oid_ordering() {
    let oid1: Oid = "1.3.6.1".parse().unwrap();
    let oid2: Oid = "1.3.6.2".parse().unwrap();
    let oid3: Oid = "1.3.6.1.1".parse().unwrap();

    assert!(oid1 < oid2);
    assert!(oid1 < oid3);
}

#[test]
fn test_trie_get_next_walk() {
    let mut trie = OidTrie::new();

    // Simulate a simple MIB table
    let oids = ["1.3.6.1.1", "1.3.6.1.2", "1.3.6.1.3", "1.3.6.1.4"];
    for (i, s) in oids.iter().enumerate() {
        let oid: Oid = s.parse().unwrap();
        trie.insert(&oid, i);
    }

    // Walk through using get_next
    let start: Oid = "1.3.6.1".parse().unwrap();
    let (next, _) = trie.get_next(&start).unwrap();
    assert_eq!(next.to_string(), "1.3.6.1.1");
}
