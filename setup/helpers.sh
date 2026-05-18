set_property() {
  local key=$1 value=$2 file=$3
  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$file"
  else
    echo "${key}=${value}" >> "$file"
  fi
}

add_newlines() {
  local n=$1 file=$2
  for ((i=0; i<n; i++)); do
    echo >> "$file"
  done
}

add_comment() {
  local comment=$1 file=$2
  echo "# ${comment}" >> "$file"
}

make_compiler_list() {
  local prefix=$1 versions=$2 list=""
  for v in $versions; do
    list="${list:+${list}:}${prefix}${v}"
  done
  echo "$list"
}
