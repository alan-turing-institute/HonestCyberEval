#! /bin/bash

CURL="curl -v --location --silent --user 00000000-0000-0000-0000-000000000000:secret"

until $CURL ${AIXCC_API_HOSTNAME}/health/ >/dev/null; do
	echo "Waiting for API to be available"
	sleep 5
	((c++)) && ((c == 12)) && exit 1
done

echo "Health check:"
set -x
$CURL ${AIXCC_API_HOSTNAME}/health/ | jq
set +x
echo ""

echo "Submitting VDS"
set -x
$CURL -X POST -H "Content-Type: application/json" ${AIXCC_API_HOSTNAME}/submission/vds/ -d '{"cp_name": "mock-cp", "pou": {"commit_sha1": "451dfb089f10ae0b5afd091a428e8c501c8b9b45", "sanitizer": "id_1"}, "pov": {"harness": "id_1", "data": "YWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmYWJjZGVmCmIKCjEK"}}' >vds.json
set +x
jq <vds.json
echo ""

VDS_UUID=$(jq <vds.json -r '.vd_uuid')
STATUS=$(jq <vds.json -r '.status')

while [ "$STATUS" == "pending" ]; do
	sleep 10
	echo "VDS status:"
	set -x
	$CURL "${AIXCC_API_HOSTNAME}/submission/vds/${VDS_UUID}" >vds.json
	set +x
	jq <vds.json
	echo ""
	STATUS=$(jq <vds.json -r '.status')
done

echo "Final VDS Status: ${STATUS}"
if [ "$STATUS" == "rejected" ]; then
	exit 1
fi
