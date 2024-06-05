#! /bin/bash

echo "The following is a demonstration of a fake CRS interacting with the competition API (cAPI).  First, we'll make sure the cAPI is available."

CURL="curl --location --silent --user 00000000-0000-0000-0000-000000000000:secret"

until $CURL ${AIXCC_API_HOSTNAME}/health/ >/dev/null; do
	echo "Waiting for the cAPI to be available..."
	sleep 5
	((c++)) && ((c == 12)) && exit 1
done

echo "Let's run a cAPI health check before we get started."
set -x
$CURL ${AIXCC_API_HOSTNAME}/health/ | jq
set +x
echo ""

echo "In this example, we're using an example challenge problem vulnerability (CPV) in the Mock CP, so we already know the answers."
echo "A real CRS will be evaluating the problem, with the help of an LLM, at this point."
echo "We're going to pretend our fake CRS has found a vulnerability in the mock challenge problem (Mock CP).  Let's go ahead and submit it."
set -x
$CURL -X POST -H "Content-Type: application/json" ${AIXCC_API_HOSTNAME}/submission/vds/ -d "{\"cp_name\": \"Mock CP\", \"pou\": {\"commit_sha1\": \"9d38fc63bb9ffbc65f976cbca45e096bad3b30e1\", \"sanitizer\": \"id_1\"}, \"pov\": {\"harness\": \"id_1\", \"data\": \"$(
	base64 -w 0 <<-'EOF'
		abcdefabcdefabcdefabcdefabcdefabcdef
		b

		1
	EOF
)\"}}" >vds.json
set +x
jq <vds.json
VDS_UUID=$(jq <vds.json -r '.vd_uuid')
echo ""

echo "The cAPI is now evaluating our Vulnerability Discovery Submission (VDS).  Its status will be pending until the cAPI runs all the tests."
$CURL "${AIXCC_API_HOSTNAME}/submission/vds/${VDS_UUID}" >vds.json
STATUS=$(jq <vds.json -r '.status')
while [ "$STATUS" == "pending" ]; do
	sleep 10
	echo "Waiting for VDS to finish testing..."
	set -x
	$CURL "${AIXCC_API_HOSTNAME}/submission/vds/${VDS_UUID}" >vds.json
	set +x
	jq <vds.json
	echo ""
	STATUS=$(jq <vds.json -r '.status')
done

echo "At this point, the VDS has been fully tested.  It could either be accepted or rejected."
echo "Final VDS Status: ${STATUS}"
if [ "$STATUS" == "rejected" ]; then
	echo "Our VDS was rejected, so we've got to start over."
	exit 1
fi
echo "Our VDS was accepted, so we should move on to producing a Generated Patch (GP)."
echo "A real CRS will be asking an LLM to produce the patch file now."

CPV_UUID=$(jq <vds.json -r '.cpv_uuid')
echo ""
echo "We're still using the example CPV, so we've got a working generated patch.  We'll submit that now:"
set -x
$CURL -X POST -H "Content-Type: application/json" ${AIXCC_API_HOSTNAME}/submission/gp/ -d "{\"cpv_uuid\": \"${CPV_UUID}\", \"data\": \"$(
	base64 -w 0 <<-'EOF'
		diff --git a/mock_vp.c b/mock_vp.c
		index 56cf8fd..abb73cd 100644
		--- a/mock_vp.c
		+++ b/mock_vp.c
		@@ -11,7 +11,8 @@ int main()
		         printf("input item:");
		         buff = &items[i][0];
		         i++;
		-        fgets(buff, 40, stdin);
		+        fgets(buff, 9, stdin);
		+        if (i==3){buff[0]= 0;}
		         buff[strcspn(buff, "\n")] = 0;
		     }while(strlen(buff)!=0);
		     i--;
	EOF
)\"}" >gp.json
set +x
jq <gp.json
GP_UUID=$(jq <gp.json -r '.gp_uuid')
echo ""

echo "Now we're going to let the cAPI evaluate our GP."
$CURL "${AIXCC_API_HOSTNAME}/submission/gp/${GP_UUID}" >gp.json
STATUS=$(jq <gp.json -r '.status')
while [ "$STATUS" == "pending" ]; do
	sleep 10
	echo "Waiting for GP to finish testing..."
	set -x
	$CURL "${AIXCC_API_HOSTNAME}/submission/gp/${GP_UUID}" >gp.json
	set +x
	jq <gp.json
	echo ""
	STATUS=$(jq <gp.json -r '.status')
done

echo "The cAPI has finished testing our GP.  As with the VDS, our GP could be accepted or rejected at this point."
echo "Final GP Status: ${STATUS}"
echo "For more information on what was done here, there are logs available in docker-compose, as well as an audit log that the cAPI produced."
echo "Look at the outputs of \`make logs-nofollow\` (for all the services) and \`make logs-crs-nofollow\` (for the CRS's logs only)."
echo "There are a few other make targets available to show you logs for crs-sandbox, including \`make logs-capi-audit\`."
