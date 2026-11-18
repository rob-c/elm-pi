---
name: hep-literature-and-data
description: "Finding and citing particle-physics sources - INSPIRE-HEP, arXiv, HEPData, the PDG and CDS: searches, APIs, BibTeX keys; never a recalled reference; record the query and the date."
disable-model-invocation: true
---

# Particle-physics literature and data sources

A reference recalled from memory is unverified even when it looks right:
authors, year, journal and arXiv number are each plausible and together
often wrong, and a number attributed to an edition of the PDG nobody opened
is a fabricated citation. Every reference in a result was retrieved in this
session, or is marked as not verified.

## Where each kind of fact lives

| Need | Source |
|---|---|
| papers, citation counts, BibTeX | INSPIRE-HEP, inspirehep.net |
| preprint text and versions | arXiv, arxiv.org |
| the numbers behind plots; likelihoods | HEPData, hepdata.net |
| particle properties, averages, reviews | PDG, pdg.lbl.gov (pdgLive) |
| theses, conference and internal notes | CDS, cds.cern.ch; experiments' public-results pages |
| heavy-flavour and lattice averages | HFLAV and FLAG |

## INSPIRE

- Search fields: `a` author, `t` title, `eprint`, `texkey`, `collaboration`,
  `j` journal, `date`, `topcite`, `refersto`, combined with and/or/not - for
  example `a <surname> and t "<title words>" and date > 2020`.
- API: `https://inspirehep.net/api/literature?q=<query>&size=25&sort=mostrecent&fields=titles,authors.full_name,arxiv_eprints,dois,texkeys`
  returns JSON, records under `hits.hits`. By identifier:
  `https://inspirehep.net/api/arxiv/<arXiv id>` and
  `https://inspirehep.net/api/doi/<doi>`. URL-encode the query.
- BibTeX: add `format=bibtex` to either. Use INSPIRE's entry and key
  (the texkey, of the form `Author:2012abc`) unchanged: collaborators'
  bibliographies use the same keys. Never compose a key or an entry by hand.
- It is rate-limited: one query with a larger `size` beats many small ones.

## arXiv

- API: `http://export.arxiv.org/api/query?search_query=<terms>&start=0&max_results=20`
  returns Atom XML; terms take prefixes `au:`, `ti:`, `abs:`, `cat:hep-ph`;
  `id_list=<ids>` fetches known papers. Leave a few seconds between calls.
- A preprint has versions: cite the one read if the numbers changed, and
  prefer the journal DOI with the arXiv number once published.

## HEPData

- Search: `https://www.hepdata.net/search/?q=<query>&format=json`. A record
  by its INSPIRE number: `https://www.hepdata.net/record/ins<number>?format=json`,
  which lists its tables and their download links (YAML, CSV, ROOT, YODA).
- Tables carry statistical and each systematic uncertainty separately, and
  sometimes covariance matrices and full likelihoods: use them instead of
  reading points off a figure. Cite the record's DOI and version.

## PDG

- pdgLive has the current listings; values change between editions, so
  quote the edition and the date read.
- Offline, the Scikit-HEP `particle` package bundles PDG tables
  (`Particle.from_pdgid(211).mass`, in MeV) and says which edition its data
  file is. The PDG's own `pdg` Python package gives the full listings.
  Check attribute names with help() - do not guess them.
- The order of preference among sources is in `physical-constants`.

## Access from a session

These sites need the network: a session with web access (`pi --remote`), or a host this install's proxy allows; a 403 otherwise is the
proxy, not the site. Without access, say so, mark each reference "(from
memory, unverified)" with no identifier you did not read, and list the
queries that would settle it.

## Recording a source

- The query, the service and the date, so that it can be repeated.
- The identifier: INSPIRE record or texkey, arXiv number with version, DOI,
  HEPData DOI.
- For a number: the table, equation or page, read in the paper itself - a
  title or an abstract is not evidence of what a paper measured.
- Preprint or published; errata; whether a later result supersedes it.

## Check before reporting

- Every reference was retrieved in this session, or is marked unverified.
- BibTeX entries are INSPIRE's own, keys unchanged.
- Each quoted value has edition or version, and where in the source it is.
- Queries and dates are recorded in the notes or the report.

## Related

- Skills here: `physical-constants`, `physics-documents`,
  `hep-reinterpretation`, `hep-data-formats`, `nuclear-data-lookup`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `literature-review`, `citation-management`, `paper-lookup`.
