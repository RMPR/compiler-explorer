NODE_VERSION=24
GCC_VERSIONS=$(seq 9 14)
LLVM_VERSIONS=$(seq 10 22)


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


# Create service
sed -e "s|SCRIPT_DIR_PLACEHOLDER|$SCRIPT_DIR|g" \
    "$SCRIPT_DIR/compiler-explorer.service" \
    | sudo tee /etc/systemd/system/compiler-explorer.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable compiler-explorer.service


# Run Compiler Explorer
cd ..
make EXTRA_ARGS='--language c++'
cd -