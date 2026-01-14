mod trie;

pub use trie::OidTrie;

use std::fmt;
use std::str::FromStr;

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Oid {
    parts: Vec<u32>,
}

#[pymethods]
impl Oid {
    #[new]
    fn py_new(s: &str) -> PyResult<Self> {
        s.parse()
            .map_err(|e: OidError| PyValueError::new_err(e.to_string()))
    }

    fn __str__(&self) -> String {
        self.to_string()
    }

    fn __repr__(&self) -> String {
        format!("Oid('{self}')")
    }

    fn __len__(&self) -> usize {
        self.parts.len()
    }

    fn __richcmp__(&self, other: &Self, op: pyo3::pyclass::CompareOp) -> bool {
        match op {
            pyo3::pyclass::CompareOp::Lt => self < other,
            pyo3::pyclass::CompareOp::Le => self <= other,
            pyo3::pyclass::CompareOp::Eq => self == other,
            pyo3::pyclass::CompareOp::Ne => self != other,
            pyo3::pyclass::CompareOp::Gt => self > other,
            pyo3::pyclass::CompareOp::Ge => self >= other,
        }
    }

    fn __hash__(&self) -> u64 {
        use std::hash::{Hash, Hasher};
        let mut hasher = std::collections::hash_map::DefaultHasher::new();
        self.hash(&mut hasher);
        hasher.finish()
    }

    #[getter]
    fn get_parts(&self) -> Vec<u32> {
        self.parts.clone()
    }

    #[pyo3(name = "starts_with")]
    fn py_starts_with(&self, prefix: &Oid) -> bool {
        self.parts.starts_with(&prefix.parts)
    }

    #[pyo3(name = "is_parent_of")]
    fn py_is_parent_of(&self, other: &Oid) -> bool {
        other.parts.len() > self.parts.len() && other.parts.starts_with(&self.parts)
    }

    #[pyo3(name = "parent")]
    fn py_parent(&self) -> Option<Oid> {
        if self.parts.len() <= 1 {
            return None;
        }
        Some(Oid {
            parts: self.parts[..self.parts.len() - 1].to_vec(),
        })
    }

    #[pyo3(name = "child")]
    fn py_child(&self, sub_id: u32) -> Oid {
        let mut parts = self.parts.clone();
        parts.push(sub_id);
        Oid { parts }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OidError {
    Empty,
    InvalidFormat(String),
    InvalidPart(String),
}

impl fmt::Display for OidError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OidError::Empty => write!(f, "OID cannot be empty"),
            OidError::InvalidFormat(s) => write!(f, "invalid OID format: {s}"),
            OidError::InvalidPart(s) => write!(f, "invalid OID part: {s}"),
        }
    }
}

impl std::error::Error for OidError {}

impl Oid {
    pub fn new(parts: Vec<u32>) -> Result<Self, OidError> {
        if parts.is_empty() {
            return Err(OidError::Empty);
        }
        Ok(Self { parts })
    }

    pub fn from_slice(parts: &[u32]) -> Result<Self, OidError> {
        Self::new(parts.to_vec())
    }

    pub fn parts(&self) -> &[u32] {
        &self.parts
    }

    pub fn len(&self) -> usize {
        self.parts.len()
    }

    pub fn is_empty(&self) -> bool {
        self.parts.is_empty()
    }

    pub fn starts_with(&self, prefix: &Oid) -> bool {
        self.parts.starts_with(&prefix.parts)
    }

    pub fn is_parent_of(&self, other: &Oid) -> bool {
        other.parts.len() > self.parts.len() && other.parts.starts_with(&self.parts)
    }

    pub fn parent(&self) -> Option<Oid> {
        if self.parts.len() <= 1 {
            return None;
        }
        Some(Oid {
            parts: self.parts[..self.parts.len() - 1].to_vec(),
        })
    }

    pub fn child(&self, sub_id: u32) -> Oid {
        let mut parts = self.parts.clone();
        parts.push(sub_id);
        Oid { parts }
    }

    pub fn common_prefix_len(&self, other: &Oid) -> usize {
        self.parts
            .iter()
            .zip(other.parts.iter())
            .take_while(|(a, b)| a == b)
            .count()
    }
}

impl FromStr for Oid {
    type Err = OidError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        let s = s.trim();
        let s = s.strip_prefix('.').unwrap_or(s);

        if s.is_empty() {
            return Err(OidError::Empty);
        }

        let parts: Result<Vec<u32>, _> = s
            .split('.')
            .map(|part| {
                part.parse::<u32>()
                    .map_err(|_| OidError::InvalidPart(part.to_string()))
            })
            .collect();

        Self::new(parts?)
    }
}

impl fmt::Display for Oid {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let s: Vec<String> = self.parts.iter().map(|p| p.to_string()).collect();
        write!(f, "{}", s.join("."))
    }
}

impl PartialOrd for Oid {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for Oid {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.parts.cmp(&other.parts)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_basic() {
        let oid: Oid = "1.3.6.1".parse().unwrap();
        assert_eq!(oid.parts(), &[1, 3, 6, 1]);
    }

    #[test]
    fn test_parse_leading_dot() {
        let oid: Oid = ".1.3.6.1".parse().unwrap();
        assert_eq!(oid.parts(), &[1, 3, 6, 1]);
    }

    #[test]
    fn test_parse_empty() {
        let result: Result<Oid, _> = "".parse();
        assert!(matches!(result, Err(OidError::Empty)));
    }

    #[test]
    fn test_parse_invalid() {
        let result: Result<Oid, _> = "1.3.abc.1".parse();
        assert!(matches!(result, Err(OidError::InvalidPart(_))));
    }

    #[test]
    fn test_display() {
        let oid: Oid = "1.3.6.1.4.1".parse().unwrap();
        assert_eq!(oid.to_string(), "1.3.6.1.4.1");
    }

    #[test]
    fn test_comparison() {
        let oid1: Oid = "1.3.6.1".parse().unwrap();
        let oid2: Oid = "1.3.6.2".parse().unwrap();
        let oid3: Oid = "1.3.6.1.1".parse().unwrap();

        assert!(oid1 < oid2);
        assert!(oid1 < oid3);
        assert!(oid2 > oid3);
    }

    #[test]
    fn test_starts_with() {
        let oid: Oid = "1.3.6.1.4.1.12345".parse().unwrap();
        let prefix: Oid = "1.3.6.1".parse().unwrap();
        let not_prefix: Oid = "1.3.6.2".parse().unwrap();

        assert!(oid.starts_with(&prefix));
        assert!(!oid.starts_with(&not_prefix));
    }

    #[test]
    fn test_parent_child() {
        let oid: Oid = "1.3.6.1".parse().unwrap();
        let parent = oid.parent().unwrap();
        let child = oid.child(4);

        assert_eq!(parent.to_string(), "1.3.6");
        assert_eq!(child.to_string(), "1.3.6.1.4");
    }

    #[test]
    fn test_is_parent_of() {
        let parent: Oid = "1.3.6.1".parse().unwrap();
        let child: Oid = "1.3.6.1.4".parse().unwrap();
        let sibling: Oid = "1.3.6.2".parse().unwrap();

        assert!(parent.is_parent_of(&child));
        assert!(!parent.is_parent_of(&sibling));
        assert!(!parent.is_parent_of(&parent));
    }
}
