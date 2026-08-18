# Homebrew formula for OfferPrinter.
#
# This file lives here as the source of truth; copy it into a tap repository
# named `homebrew-tap` under the same GitHub account to make this work:
#
#   brew tap mohitagw15856/tap
#   brew install offerprinter
#
# After each release, update `url` and `sha256` to point at the new sdist on
# PyPI. Get the checksum with:
#
#   curl -sL <url> | shasum -a 256
#
# `brew update-python-resources Formula/offerprinter.rb` regenerates the
# resource blocks below from the package metadata.

class Offerprinter < Formula
  include Language::Python::Virtualenv

  desc "Print a tailored CV, cover letter, fit memo and ATS report from one job description"
  homepage "https://github.com/mohitagw15856/OfferPrinter"
  url "https://files.pythonhosted.org/packages/source/o/offerprinter/offerprinter-0.2.0.tar.gz"
  sha256 "REPLACE_WITH_SDIST_SHA256"
  license "MIT"
  head "https://github.com/mohitagw15856/OfferPrinter.git", branch: "main"

  depends_on "python@3.12"

  # Generated with: brew update-python-resources Formula/offerprinter.rb
  # Left empty here so the formula fails loudly rather than silently installing
  # a stale dependency set.

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      OfferPrinter needs an LLM API key. Set one of:

        export ANTHROPIC_API_KEY="sk-ant-..."   # default provider
        export OPENAI_API_KEY="sk-..."
        export GEMINI_API_KEY="..."
        export MOONSHOT_API_KEY="..."

      Or run it with no key at all against a local model:

        ollama pull llama3.1
        offerprinter --provider ollama --cv cv.pdf --jd-file jd.txt
    EOS
  end

  test do
    assert_match "OfferPrinter", shell_output("#{bin}/offerprinter --version")
  end
end
