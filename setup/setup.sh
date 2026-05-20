NODE_VERSION=24

GCC_LATEST=${1:-14}
LLVM_LATEST=${2:-22}
GCC_VERSIONS=$(seq 9 $GCC_LATEST)
LLVM_VERSIONS=$(seq 15 $LLVM_LATEST)

PROPS="etc/config/c++.defaults.properties"
SETUP_TMPDIR="/tmp/ce-setup"
DEPSDIR="/opt/dependencies"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CE_USER="$(whoami)"


source "$(dirname "$0")/helpers.sh"
mkdir -p "$SETUP_TMPDIR"
mkdir -p "$DEPSDIR"


# Install NodeJS
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash
\. "$HOME/.nvm/nvm.sh"
nvm install $NODE_VERSION


# Setup NSJail
sudo apt-get install -y \
  autoconf bison flex gcc g++ git libprotobuf-dev \
  libnl-route-3-dev libtool make pkg-config protobuf-compiler

git clone https://github.com/compiler-explorer/nsjail.git "$SETUP_TMPDIR/nsjail"
cd "$SETUP_TMPDIR/nsjail"
git checkout ce
make
sudo cp nsjail /usr/local/bin/nsjail
cd -


# Setup Cgroups
sudo bash "$SCRIPT_DIR/ce-cgroups.sh"

sed -e "s|SCRIPT_DIR_PLACEHOLDER|$SCRIPT_DIR|g" \
    -e "s|CE_USER_PLACEHOLDER|$CE_USER|g" \
    "$SCRIPT_DIR/ce-cgroups.service" \
    | sudo tee /etc/systemd/system/ce-cgroups.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable ce-cgroups.service


# Install GCC
sudo apt install -y lsb-release wget software-properties-common gnupg
sudo add-apt-repository -y ppa:ubuntu-toolchain-r/test

for GCC_VERSION in $GCC_VERSIONS; do
  sudo apt install -y g++-${GCC_VERSION}
done

add_newlines 2 "$PROPS"
add_comment "GCC Compilers" "$PROPS"
set_property "group.gcc.compilers" "$(make_compiler_list g "$GCC_VERSIONS")" "$PROPS"
for GCC_VERSION in $GCC_VERSIONS; do
  set_property "compiler.g${GCC_VERSION}.exe" "/usr/bin/g++-${GCC_VERSION}" "$PROPS"
  set_property "compiler.g${GCC_VERSION}.name" "g++ ${GCC_VERSION}" "$PROPS"
done


# Install LLVM
wget -qO "$SETUP_TMPDIR/llvm.sh" https://apt.llvm.org/llvm.sh

for LLVM_VERSION in $LLVM_VERSIONS; do
  sudo bash "$SETUP_TMPDIR/llvm.sh" $LLVM_VERSION
done

rm "$SETUP_TMPDIR/llvm.sh"

add_newlines 2 "$PROPS"
add_comment "Clang Compilers" "$PROPS"
set_property "group.clang.compilers" "$(make_compiler_list clang "$LLVM_VERSIONS")" "$PROPS"
for LLVM_VERSION in $LLVM_VERSIONS; do
  set_property "compiler.clang${LLVM_VERSION}.exe" "/usr/bin/clang++-${LLVM_VERSION}" "$PROPS"
  set_property "compiler.clang${LLVM_VERSION}.name" "clang ${LLVM_VERSION}" "$PROPS"
done

# For old versions of LLVM we cannot rely on APT so just get the binaries from the GitHub releases directly.
sudo apt-get install -y libncurses5
OLD_LLVM_VERSIONS=""
while IFS= read -r url || [ -n "$url" ]; do
  tarball="$SETUP_TMPDIR/$(basename "$url")"
  wget -qO "$tarball" "$url"

  version=$(basename "$tarball" | sed 's/clang+llvm-\([0-9.]*\)-.*/\1/')
  major="${version%%.*}"
  dest="/opt/llvm/$major"

  mkdir -p "$dest"
  tar -xf "$tarball" -C "$dest" --strip-components=1
  rm "$tarball"

  ln -sf "$dest/bin/clang++" "/usr/bin/clang++-$major"

  set_property "compiler.clang${major}.exe" "/usr/bin/clang++-${major}" "$PROPS"
  set_property "compiler.clang${major}.name" "clang ${major}" "$PROPS"

  OLD_LLVM_VERSIONS="${OLD_LLVM_VERSIONS:+${OLD_LLVM_VERSIONS} }${major}"
done < "$(dirname "$0")/llvm_urls.txt"

current_clangs=$(get_property "group.clang.compilers" "$PROPS")
set_property "group.clang.compilers" "${current_clangs}:$(make_compiler_list clang "$OLD_LLVM_VERSIONS")" "$PROPS"


# Install Zivid SDKs
# Versions to install are taken from sdk_urls.txt
while IFS= read -r url; do
  deb="$SETUP_TMPDIR/$(basename "$url")"
  wget -qO "$deb" "$url"
  version=$(basename "$deb" .deb | sed 's/^[^_]*_\([^+]*\).*/\1/')
  dest="$DEPSDIR/zivid-sdk/$version"
  mkdir -p "$dest"
  dpkg -x "$deb" "$dest"
  rm "$deb"
done < "$(dirname "$0")/sdk_urls.txt"

# We have an extra 'usr' folder in the folder structure that is not there for Conan packages.
# Remove it so the Zivid package has the same format as the other dependencies.
for sdk_dir in "$DEPSDIR/zivid-sdk"/*/; do
  for subdir in include lib; do
    [ -d "$sdk_dir/usr/$subdir" ] && mv "$sdk_dir/usr/$subdir" "$sdk_dir/$subdir"
  done
  rm -rf "$sdk_dir/usr"
done


# Install Conan packages
sudo apt-get install -y python3 python3-venv cmake ninja-build jq
python3 -m venv "$SETUP_TMPDIR/venv"
source "$SETUP_TMPDIR/venv/bin/activate"
pip install conan
conan profile detect
conan install "$SCRIPT_DIR/conanfile.txt" --build=missing --deployer=full_deploy --deployer-folder="$SETUP_TMPDIR/conan"

# We want to copy the bin, lib and include folders for each package to $DEPSDIR/<package>/<version>.
# We can query Conan to find out where they are installed. This can differ between packages.
PKG_REFS=$(conan list "*:*" --format=json | jq -r '
  .["Local Cache"] | to_entries[] |
  (.key | split("/")) as [$name, $version] |
  .value.revisions | to_entries[] |
  .value.packages // {} | keys[] |
  "\($name) \($version) \($name)/\($version):\(.)"
')

while read -r name version ref; do
  pkg_path=$(conan cache path "$ref")
  dest="$DEPSDIR/$name/$version"

  for subdir in bin lib include; do
    if [ -d "$pkg_path/$subdir" ]; then
      mkdir -p "$dest/$subdir"
      cp -r "$pkg_path/$subdir/." "$dest/$subdir/"
    fi
  done
done <<< "$PKG_REFS"


# Add dependencies to CE
add_newlines 2 "$PROPS"
add_comment "Libraries" "$PROPS"

CONAN_LIBS=""
for pkg_dir in "$DEPSDIR"/*/; do
  name=$(basename "$pkg_dir")

  versions_list=""
  for version_dir in "$pkg_dir"*/; do
    # Skip folders that don't match expected folder structure (at least having an include subdirectory).
    [ -d "${version_dir}include" ] || continue

    version=$(basename "$version_dir")
    vkey="${version//./}" # Remove dots
    versions_list="${versions_list:+${versions_list}:}${vkey}"

    set_property "libs.${name}.versions.${vkey}.version" "$version" "$PROPS"
    set_property "libs.${name}.versions.${vkey}.path" "${version_dir}include" "$PROPS"
    set_property "libs.${name}.versions.${vkey}.libpath" "${version_dir}lib" "$PROPS"
  done

  [ -n "$versions_list" ] || continue

  set_property "libs.${name}.name" "$name" "$PROPS"
  set_property "libs.${name}.versions" "$versions_list" "$PROPS"
  add_newlines 1 "$PROPS"

  CONAN_LIBS="${CONAN_LIBS:+${CONAN_LIBS}:}${name}"
done

set_property "libs" "${CONAN_LIBS}" "$PROPS"


# Create service
sed -e "s|SCRIPT_DIR_PLACEHOLDER|$SCRIPT_DIR|g" \
    "$SCRIPT_DIR/compiler-explorer.service" \
    | sudo tee /etc/systemd/system/compiler-explorer.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable compiler-explorer.service


# Run Compiler Explorer
cd "$SCRIPT_DIR/.."
make EXTRA_ARGS='--language c++'