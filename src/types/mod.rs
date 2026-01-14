use std::fmt;
use std::net::Ipv4Addr;

use crate::oid::Oid;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Integer(i32),
    OctetString(Vec<u8>),
    Null,
    ObjectIdentifier(Oid),
    IpAddress(Ipv4Addr),
    Counter32(u32),
    Gauge32(u32),
    TimeTicks(u32),
    Opaque(Vec<u8>),
    Counter64(u64),
    NoSuchObject,
    NoSuchInstance,
    EndOfMibView,
}

impl Value {
    pub fn integer(v: i32) -> Self {
        Value::Integer(v)
    }

    pub fn octet_string(v: impl Into<Vec<u8>>) -> Self {
        Value::OctetString(v.into())
    }

    pub fn string(s: &str) -> Self {
        Value::OctetString(s.as_bytes().to_vec())
    }

    pub fn oid(o: Oid) -> Self {
        Value::ObjectIdentifier(o)
    }

    pub fn ip_address(addr: Ipv4Addr) -> Self {
        Value::IpAddress(addr)
    }

    pub fn counter32(v: u32) -> Self {
        Value::Counter32(v)
    }

    pub fn gauge32(v: u32) -> Self {
        Value::Gauge32(v)
    }

    pub fn timeticks(v: u32) -> Self {
        Value::TimeTicks(v)
    }

    pub fn opaque(v: impl Into<Vec<u8>>) -> Self {
        Value::Opaque(v.into())
    }

    pub fn counter64(v: u64) -> Self {
        Value::Counter64(v)
    }

    pub fn type_name(&self) -> &'static str {
        match self {
            Value::Integer(_) => "Integer",
            Value::OctetString(_) => "OctetString",
            Value::Null => "Null",
            Value::ObjectIdentifier(_) => "ObjectIdentifier",
            Value::IpAddress(_) => "IpAddress",
            Value::Counter32(_) => "Counter32",
            Value::Gauge32(_) => "Gauge32",
            Value::TimeTicks(_) => "TimeTicks",
            Value::Opaque(_) => "Opaque",
            Value::Counter64(_) => "Counter64",
            Value::NoSuchObject => "NoSuchObject",
            Value::NoSuchInstance => "NoSuchInstance",
            Value::EndOfMibView => "EndOfMibView",
        }
    }

    pub fn as_integer(&self) -> Option<i32> {
        match self {
            Value::Integer(v) => Some(*v),
            _ => None,
        }
    }

    pub fn as_octet_string(&self) -> Option<&[u8]> {
        match self {
            Value::OctetString(v) => Some(v),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::OctetString(v) => std::str::from_utf8(v).ok(),
            _ => None,
        }
    }

    pub fn as_oid(&self) -> Option<&Oid> {
        match self {
            Value::ObjectIdentifier(o) => Some(o),
            _ => None,
        }
    }

    pub fn as_counter32(&self) -> Option<u32> {
        match self {
            Value::Counter32(v) => Some(*v),
            _ => None,
        }
    }

    pub fn as_counter64(&self) -> Option<u64> {
        match self {
            Value::Counter64(v) => Some(*v),
            _ => None,
        }
    }
}

impl fmt::Display for Value {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Value::Integer(v) => write!(f, "{v}"),
            Value::OctetString(v) => {
                if let Ok(s) = std::str::from_utf8(v) {
                    write!(f, "{s}")
                } else {
                    write!(f, "{v:?}")
                }
            }
            Value::Null() => write!(f, "NULL"),
            Value::ObjectIdentifier(o) => write!(f, "{o}"),
            Value::IpAddress(a, b, c, d) => write!(f, "{a}.{b}.{c}.{d}"),
            Value::Counter32(v) => write!(f, "{v}"),
            Value::Gauge32(v) => write!(f, "{v}"),
            Value::TimeTicks(v) => write!(f, "{v}"),
            Value::Opaque(v) => write!(f, "{v:?}"),
            Value::Counter64(v) => write!(f, "{v}"),
            Value::NoSuchObject() => write!(f, "noSuchObject"),
            Value::NoSuchInstance() => write!(f, "noSuchInstance"),
            Value::EndOfMibView() => write!(f, "endOfMibView"),
        }
    }
}

impl From<i32> for Value {
    fn from(v: i32) -> Self {
        Value::Integer(v)
    }
}

impl From<&str> for Value {
    fn from(s: &str) -> Self {
        Value::OctetString(s.as_bytes().to_vec())
    }
}

impl From<String> for Value {
    fn from(s: String) -> Self {
        Value::OctetString(s.into_bytes())
    }
}

impl From<Vec<u8>> for Value {
    fn from(v: Vec<u8>) -> Self {
        Value::OctetString(v)
    }
}

impl From<Oid> for Value {
    fn from(o: Oid) -> Self {
        Value::ObjectIdentifier(o)
    }
}

impl From<Ipv4Addr> for Value {
    fn from(addr: Ipv4Addr) -> Self {
        Value::IpAddress(addr)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_integer() {
        let v = Value::integer(42);
        assert_eq!(v.as_integer(), Some(42));
        assert_eq!(v.type_name(), "Integer");
        assert_eq!(v.to_string(), "42");
    }

    #[test]
    fn test_octet_string() {
        let v = Value::string("hello");
        assert_eq!(v.as_str(), Some("hello"));
        assert_eq!(v.type_name(), "OctetString");
    }

    #[test]
    fn test_counter64() {
        let v = Value::counter64(u64::MAX);
        assert_eq!(v.as_counter64(), Some(u64::MAX));
        assert_eq!(v.type_name(), "Counter64");
    }

    #[test]
    fn test_ip_address() {
        let addr = Ipv4Addr::new(192, 168, 1, 1);
        let v = Value::ip_address(addr);
        assert_eq!(v.to_string(), "192.168.1.1");
    }

    #[test]
    fn test_oid_value() {
        let oid: Oid = "1.3.6.1.4.1".parse().unwrap();
        let v = Value::oid(oid.clone());
        assert_eq!(v.as_oid(), Some(&oid));
    }

    #[test]
    fn test_from_conversions() {
        let v1: Value = 42.into();
        assert_eq!(v1.as_integer(), Some(42));

        let v2: Value = "test".into();
        assert_eq!(v2.as_str(), Some("test"));

        let v3: Value = Ipv4Addr::new(10, 0, 0, 1).into();
        assert_eq!(v3.to_string(), "10.0.0.1");
    }
}
