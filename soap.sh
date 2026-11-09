#!/bin/bash
# soap.sh <url> <operation> <inner xml>  -> raw SOAP response from İBB's open-data services
curl -s -m 120 -X POST "$1" -H 'Content-Type: text/xml; charset=utf-8' -H "SOAPAction: \"http://tempuri.org/$2\"" \
  --data-binary "<?xml version=\"1.0\" encoding=\"utf-8\"?><soap:Envelope xmlns:soap=\"http://schemas.xmlsoap.org/soap/envelope/\"><soap:Body><$2 xmlns=\"http://tempuri.org/\">$3</$2></soap:Body></soap:Envelope>"
