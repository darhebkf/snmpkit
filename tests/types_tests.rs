use snmpkit::oid::Oid;
use snmpkit::types::Value;

#[test]
fn test_value_types() {
    let int_val = Value::integer(-100);
    let str_val = Value::string("test string");
    let counter = Value::counter64(1_000_000);

    assert_eq!(int_val.type_name(), "Integer");
    assert_eq!(str_val.type_name(), "OctetString");
    assert_eq!(counter.type_name(), "Counter64");
}

#[test]
fn test_value_with_oid() {
    let oid: Oid = "1.3.6.1.2.1.1.1.0".parse().unwrap();
    let val = Value::oid(oid);
    assert_eq!(val.to_string(), "1.3.6.1.2.1.1.1.0");
}

#[test]
fn test_snmp_exceptions() {
    let no_such = Value::NoSuchObject;
    let end_of_mib = Value::EndOfMibView;

    assert_eq!(no_such.to_string(), "noSuchObject");
    assert_eq!(end_of_mib.to_string(), "endOfMibView");
}
