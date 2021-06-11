Available targets
<dl>
<dt><code>all</code></dt><dd>Build all of LLVM's sub-projects in the correct order.</dd>
<dt><code>all-srpms</code></dt><dd>Build all SRPMS for all of LLVM's sub-projects.<br/>
 NOTE: With "make srpm-<PROJECT> you can build an SRPM for an individual LLVM<br/>
 sub-project.</dd>
<dt><code>clean</code></dt><dd>Remove the ./out artifacts directory.<br/>
 NOTE: You can also call "make clean-<PROJECT>" to remove the artifacts for an<br/>
 individual project only.</dd>
<dt><code>clean-cache</code></dt><dd>Remove the ./dnf-cache DNF cache directory.<br/>
 NOTE: This might require to be run as root for permission problems.</dd>
<dt><code>container-image</code></dt><dd>Builds the container image that will be used for build SRPMs and RPMs.</dd>
<dt><code>python-lit</code></dt><dd>Build LLVM's python-lit sub-project.</dd>
<dt><code>compat-llvm</code></dt><dd>Build the compatibility packages for LLVM's llvm sub-project.</dd>
<dt><code>compat-clang</code></dt><dd>Build the compatibility packages for LLVM's clang sub-project.</dd>
<dt><code>llvm</code></dt><dd>Build LLVM's llvm sub-project.</dd>
<dt><code>clang</code></dt><dd>Build LLVM's clang sub-project.</dd>
<dt><code>lld</code></dt><dd>Build LLVM's lld sub-project.</dd>
<dt><code>help</code></dt><dd>Display this help text.</dd>
<dt><code>help-html</code></dt><dd>Display this help text as an HTML definition list for better documentation generation</dd>
</dl>
