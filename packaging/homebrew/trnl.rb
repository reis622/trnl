# Homebrew tap formula (repo: github.com/reis622/homebrew-tap, file Formula/trnl.rb)
# Install: brew install reis622/tap/trnl
# Fill the sha256 values from SHA256SUMS.txt of the GitHub release.
class Trnl < Formula
  desc "Fast terminal translator: online first, offline fallback (en de tr es ja zh)"
  homepage "https://github.com/reis622/trnl"
  version "1.1.0"
  license "MIT"

  on_macos do
    on_arm do
      url "https://github.com/reis622/trnl/releases/download/v#{version}/trnl-#{version}-macos-arm64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_macos-arm64"
    end
    on_intel do
      url "https://github.com/reis622/trnl/releases/download/v#{version}/trnl-#{version}-macos-x64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_macos-x64"
    end
  end
  on_linux do
    on_intel do
      url "https://github.com/reis622/trnl/releases/download/v#{version}/trnl-#{version}-linux-x64.tar.gz"
      sha256 "REPLACE_WITH_SHA256_linux-x64"
    end
  end

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"trnl"
  end

  def caveats
    <<~EOS
      Offline models and dictionaries (~1.4 GB) are downloaded once with:
        trnl --setup
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/trnl --version")
  end
end
