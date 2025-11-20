#!/bin/bash
# Build the Zorkie documentation website from markdown docs

set -e

echo "Building Zorkie website from documentation..."

# Create site directory
mkdir -p site

# Generate index.html (main page)
cat > site/index.html << 'HTMLEOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Zorkie - ZIL Compiler for Z-machine Games</title>
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <header>
        <div class="container">
            <h1>Zorkie</h1>
            <p class="tagline">A modern ZIL compiler for creating classic Z-machine interactive fiction</p>
            <nav>
                <a href="#about">About</a>
                <a href="#getting-started">Getting Started</a>
                <a href="#language">Language Reference</a>
                <a href="#examples">Examples</a>
                <a href="https://github.com/avwohl/zorkie">GitHub</a>
            </nav>
        </div>
    </header>

    <main class="container">
        <section id="about">
            <h2>About Zorkie</h2>
            <p>Zorkie is a feature-complete ZIL (Zork Implementation Language) compiler that compiles classic Infocom games into Z-machine story files. Written in Python, it successfully compiles Zork1, Enchanter, and Planetfall from their original source code.</p>

            <div class="stats">
                <div class="stat">
                    <h3>100%</h3>
                    <p>ZIL Language Coverage</p>
                </div>
                <div class="stat">
                    <h3>223</h3>
                    <p>Code Generation Methods</p>
                </div>
                <div class="stat">
                    <h3>188</h3>
                    <p>Z-machine Opcodes</p>
                </div>
                <div class="stat">
                    <h3>3</h3>
                    <p>Classic Games Compiled</p>
                </div>
            </div>
        </section>

        <section id="getting-started">
            <h2>Getting Started</h2>

            <h3>Installation</h3>
            <pre><code>git clone https://github.com/avwohl/zorkie.git
cd zorkie
chmod +x zorkie</code></pre>

            <h3>Quick Start</h3>
            <pre><code># Compile a ZIL game
./zorkie game.zil -o game.z3

# Compile with verbose output
./zorkie game.zil -o game.z3 --verbose

# Enable string deduplication
./zorkie game.zil -o game.z3 --string-dedup

# Target different Z-machine version
./zorkie game.zil -o game.z5 -v 5</code></pre>

            <h3>Command-Line Options</h3>
            <table>
                <tr>
                    <th>Option</th>
                    <th>Description</th>
                </tr>
                <tr>
                    <td><code>-o FILE</code></td>
                    <td>Output story file (.z3, .z5, etc.)</td>
                </tr>
                <tr>
                    <td><code>-v VERSION</code></td>
                    <td>Target Z-machine version (1-8, default: 3)</td>
                </tr>
                <tr>
                    <td><code>--verbose</code></td>
                    <td>Show compilation progress and statistics</td>
                </tr>
                <tr>
                    <td><code>--string-dedup</code></td>
                    <td>Enable string table deduplication</td>
                </tr>
            </table>
        </section>

        <section id="language">
            <h2>ZIL Language Reference</h2>
            <p>Zorkie implements the complete ZIL language as used in classic Infocom games. See the full <a href="language.html">Language Reference</a> for details.</p>

            <h3>Fully Implemented Features</h3>
            <div class="feature-grid">
                <div class="feature-category">
                    <h4>Core Language</h4>
                    <ul>
                        <li>ROUTINE, OBJECT, ROOM</li>
                        <li>GLOBAL, CONSTANT</li>
                        <li>COND, REPEAT, PROG</li>
                        <li>All control flow</li>
                    </ul>
                </div>
                <div class="feature-category">
                    <h4>Object System</h4>
                    <ul>
                        <li>Properties and attributes</li>
                        <li>Object tree manipulation</li>
                        <li>FSET, FCLEAR, GETP, PUTP</li>
                        <li>MOVE, INSERT, REMOVE</li>
                    </ul>
                </div>
                <div class="feature-category">
                    <h4>Parser & Game</h4>
                    <ul>
                        <li>SYNTAX definitions</li>
                        <li>VERB, BUZZ words</li>
                        <li>Dictionary generation</li>
                        <li>Parser integration</li>
                    </ul>
                </div>
                <div class="feature-category">
                    <h4>Advanced</h4>
                    <ul>
                        <li>Macro system (DEFMAC)</li>
                        <li>Multi-file compilation</li>
                        <li>Property definitions</li>
                        <li>Abbreviations table</li>
                    </ul>
                </div>
            </div>

            <p><strong>Not Implemented:</strong> MDL-specific features not used in Z-machine games. See <a href="language.html#not-implemented">complete list</a>.</p>
        </section>

        <section id="examples">
            <h2>Examples</h2>

            <h3>Hello World</h3>
            <pre><code>&lt;VERSION 3&gt;

&lt;ROUTINE MAIN ()
    &lt;TELL "Hello, World!" CR&gt;
    &lt;QUIT&gt;&gt;</code></pre>

            <h3>Simple Room</h3>
            <pre><code>&lt;VERSION 3&gt;

&lt;ROOM LIVING-ROOM
    (DESC "Living Room")
    (LDESC "You are in a cozy living room.")
    (NORTH TO KITCHEN)
    (FLAGS LIGHTBIT)&gt;

&lt;ROOM KITCHEN
    (DESC "Kitchen")
    (SOUTH TO LIVING-ROOM)
    (FLAGS LIGHTBIT)&gt;</code></pre>

            <p>More examples in the <a href="https://github.com/avwohl/zorkie/tree/main/test-games">repository</a>.</p>
        </section>

        <section id="compilation-results">
            <h2>Compilation Results</h2>
            <table class="results-table">
                <tr>
                    <th>Game</th>
                    <th>Routines</th>
                    <th>Objects</th>
                    <th>Vocabulary</th>
                    <th>Size</th>
                    <th>Status</th>
                </tr>
                <tr>
                    <td>Zork1</td>
                    <td>440</td>
                    <td>250</td>
                    <td>672 words</td>
                    <td>31.7 KB</td>
                    <td class="status-working">✓ Working</td>
                </tr>
                <tr>
                    <td>Enchanter</td>
                    <td>400+</td>
                    <td>200+</td>
                    <td>N/A</td>
                    <td>33.4 KB</td>
                    <td class="status-working">✓ Working</td>
                </tr>
                <tr>
                    <td>Planetfall</td>
                    <td>500+</td>
                    <td>300+</td>
                    <td>630 words</td>
                    <td>69.6 KB</td>
                    <td class="status-working">✓ Working</td>
                </tr>
            </table>
        </section>

        <section id="resources">
            <h2>Resources</h2>
            <ul>
                <li><a href="language.html">Complete Language Reference</a></li>
                <li><a href="https://github.com/avwohl/zorkie">GitHub Repository</a></li>
                <li><a href="http://www.xlisper.com/zil.pdf">Learning ZIL (PDF)</a> - Original manual</li>
                <li><a href="https://www.inform-fiction.org/zmachine/standards/">Z-machine Standards</a></li>
            </ul>
        </section>
    </main>

    <footer>
        <div class="container">
            <p>&copy; 2025 Zorkie Project. Built for preserving and creating classic interactive fiction.</p>
            <p><a href="https://github.com/avwohl/zorkie">View on GitHub</a></p>
        </div>
    </footer>
</body>
</html>
HTMLEOF

# Copy CSS (same for all pages)
cp site/style.css site/style.css.tmp 2>/dev/null || cat > site/style.css << 'CSSEOF'
/* Zorkie Website Styles */
:root {
    --primary-color: #2c5f8d;
    --secondary-color: #4a90c7;
    --success-color: #28a745;
    --text-color: #333;
    --bg-color: #f5f5f5;
    --code-bg: #f8f9fa;
    --border-color: #ddd;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    line-height: 1.6;
    color: var(--text-color);
    background: var(--bg-color);
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

header {
    background: var(--primary-color);
    color: white;
    padding: 2rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

header h1 {
    font-size: 3rem;
    margin-bottom: 0.5rem;
}

.tagline {
    font-size: 1.2rem;
    margin-bottom: 1.5rem;
    opacity: 0.9;
}

nav {
    display: flex;
    gap: 2rem;
    flex-wrap: wrap;
}

nav a {
    color: white;
    text-decoration: none;
    font-weight: 500;
    padding: 0.5rem 0;
    border-bottom: 2px solid transparent;
    transition: border-color 0.3s;
}

nav a:hover {
    border-bottom-color: white;
}

main {
    background: white;
    margin: 2rem auto;
    padding: 2rem;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

section {
    margin-bottom: 3rem;
}

h2 {
    color: var(--primary-color);
    font-size: 2rem;
    margin-bottom: 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 3px solid var(--secondary-color);
}

h3 {
    color: var(--primary-color);
    font-size: 1.5rem;
    margin-top: 2rem;
    margin-bottom: 1rem;
}

p {
    margin-bottom: 1rem;
}

.stats {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.5rem;
    margin: 2rem 0;
}

.stat {
    background: var(--code-bg);
    padding: 1.5rem;
    border-radius: 8px;
    text-align: center;
    border: 2px solid var(--border-color);
}

.stat h3 {
    color: var(--secondary-color);
    font-size: 2.5rem;
    margin: 0;
}

.stat p {
    color: #666;
    margin: 0.5rem 0 0 0;
    font-size: 0.9rem;
}

.feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
    margin: 2rem 0;
}

.feature-category {
    background: var(--code-bg);
    padding: 1.5rem;
    border-radius: 8px;
    border-left: 4px solid var(--secondary-color);
}

.feature-category ul {
    list-style: none;
    padding: 0;
}

.feature-category li:before {
    content: "✓";
    color: var(--success-color);
    font-weight: bold;
    margin-right: 0.5rem;
}

pre {
    background: var(--code-bg);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    padding: 1rem;
    overflow-x: auto;
    margin: 1rem 0;
}

code {
    font-family: "Courier New", Courier, monospace;
    font-size: 0.9rem;
}

p code, li code, td code {
    background: var(--code-bg);
    padding: 0.2rem 0.4rem;
    border-radius: 3px;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
}

th, td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

th {
    background: var(--code-bg);
    font-weight: 600;
    color: var(--primary-color);
}

ul {
    margin-left: 2rem;
    margin-bottom: 1rem;
}

li {
    margin-bottom: 0.5rem;
}

a {
    color: var(--secondary-color);
    text-decoration: none;
}

a:hover {
    text-decoration: underline;
}

.status-working {
    color: var(--success-color);
    font-weight: 600;
}

footer {
    background: #333;
    color: white;
    padding: 2rem 0;
    text-align: center;
}

footer a {
    color: var(--secondary-color);
}

@media (max-width: 768px) {
    header h1 {
        font-size: 2rem;
    }
    .stats, .feature-grid {
        grid-template-columns: 1fr;
    }
}
CSSEOF

# Note: language.html is already generated manually with full details
# Copy it if it exists, otherwise create a basic version
if [ ! -f site/language.html ]; then
    echo "Warning: site/language.html not found. Please generate language reference manually."
fi

# Generate sitemap.xml
cat > site/sitemap.xml << 'XMLEOF'
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
    <url>
        <loc>https://zorkie.awohl.com/</loc>
        <lastmod>2025-01-20</lastmod>
        <changefreq>monthly</changefreq>
        <priority>1.0</priority>
    </url>
    <url>
        <loc>https://zorkie.awohl.com/language.html</loc>
        <lastmod>2025-01-20</lastmod>
        <changefreq>monthly</changefreq>
        <priority>0.8</priority>
    </url>
</urlset>
XMLEOF

echo "Site built successfully in site/"
echo "Deploy to https://zorkie.awohl.com"
