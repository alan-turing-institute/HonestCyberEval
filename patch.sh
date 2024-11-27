git -C "${HOME}/aicc_crs/cp_root/nginx-cp-full/src/nginx" restore .
excluded="${HOME}/aicc_crs/cp_root/nginx-cp-full/.internal_only/cpv${1}/patches/nginx/good_patch.diff"
for dir in "${HOME}/aicc_crs/cp_root/nginx-cp-full/.internal_only/"*
do
  patch="${dir}/patches/nginx/good_patch.diff"
  if [ "$excluded" != "$patch" ]; then
    git -C "${HOME}/aicc_crs/cp_root/nginx-cp-full/src/nginx" apply "$patch"
  fi
done
