# HIP-Ref Skill Maintenance Guide

Step-by-step procedures for keeping this skill up-to-date.

## Update PDFs

AMD's CDN blocks wget. Use curl with a browser User-Agent:

```bash
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"

# ISA references
curl -L -A "$UA" -o pdfs/cdna3-isa-reference.pdf \
  "https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-mi300-cdna3-instruction-set-architecture.pdf"
curl -L -A "$UA" -o pdfs/cdna4-isa-reference.pdf \
  "https://www.amd.com/content/dam/amd/en/documents/instinct-tech-docs/instruction-set-architectures/amd-instinct-mi350-cdna4-instruction-set-architecture.pdf"

# Whitepapers — check AMD Instinct docs page for latest URLs
# Datasheets — check https://www.amd.com/en/products/accelerators/instinct.html
```

## Fix Broken Links

Check all URLs in topic files and INDEX.md:

```bash
# Extract all URLs
grep -roh 'https://[^ )]*' topics/ INDEX.md | sort -u > /tmp/urls.txt

# Test each (returns HTTP status)
while read url; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -L -A "$UA" "$url" 2>/dev/null)
  echo "$code $url"
done < /tmp/urls.txt | grep -v "^200"
```

Replace dead links with current equivalents from:
- ROCm docs: https://rocm.docs.amd.com/
- GPUOpen: https://gpuopen.com/learn/
- AMD blogs: https://rocm.blogs.amd.com/

## Update Out-of-Date Info

1. Read the latest ISA PDF (table of contents → relevant chapter)
2. Compare with the topic file's "Key numbers" section
3. Update any changed values (register counts, cache sizes, instruction lists)
4. Note the date of verification in a comment at the bottom of the topic file

## Add a New Topic

1. Create `topics/<topic-name>.md` using this template:

```markdown
# <Topic Title>

## What it is
<2-3 line explanation>

## When you care
<Practical scenarios where this matters>

## Key numbers
| Property | CDNA3 (MI300) | CDNA4 (MI350) |
|----------|---------------|---------------|
| ...      | ...           | ...           |

## How to use it
<Code patterns, intrinsic examples, tradeoff analysis>

## Pitfalls
<Common mistakes and how to avoid them>

## CDNA3 vs CDNA4 differences
<Where behavior diverges between architectures>

## Sources
- [Link text](URL)
- PDF: pdfs/<name>.pdf, Chapter X
```

2. Add an entry to `INDEX.md`:

```
## <topic-name>
Keywords: keyword1, keyword2, keyword3
Topic: topics/<topic-name>.md
PDFs: pdfs/<relevant>.pdf (Ch.X)
Links: <relevant-url>
```

## Add New PDFs

1. Download to `pdfs/` using curl (not wget)
2. Reference from relevant topic files under "Sources"
3. Add to INDEX.md entries where relevant
4. Update SKILL.md's PDF list if it's a major reference

## Verify Skill

Test these queries after any update:

1. "What MFMA instructions are available on CDNA4?"
   → Should reference topics/mfma-register-layout.md
2. "How do I reduce register pressure in my kernel?"
   → Should reference topics/occupancy-register-pressure.md and topics/vgpr-sgpr-agpr.md
3. "What's the LDS size per CU on MI300X?"
   → Should reference topics/memory-hierarchy.md or topics/hardware-specs-table.md
4. "How to use DPP for warp-level reduction?"
   → Should reference topics/cross-lane-ops.md
5. "How do I profile my FMHA kernel?"
   → Should reference topics/profiling-workflow.md
6. "What are the cache policy bits?"
   → Should reference topics/cache-policies.md
