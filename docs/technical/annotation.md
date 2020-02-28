---
Title: Annotation
---

# Annotation

Description of the annotation sources included with the service, and how to update them.

[[toc]]


## General annotation

### VEP

v98.3

#### VEP settings used in the annotation service

See /src/annotation/annotate.sh
...

#### Update

Not part of update schedule. Updating VEP might break a number of things the ELLA application, and should not be done without thorough testing.

## Population frequencies

### GnomAD

v2.0

#### Update

Not part of update schedule. From v3.0, GnomAD is only available for genome build GRCh38, which is currently incompatible with ELLA anno.

### In-house database

No in-house database is included with the service. To add your own database, you need to ...

## External mutation databases

### ClinVar

...

#### Update

Updates should be done monthtly, timed with ClinVar's releases.
 

### HGMD (Pro)

Need pro subscription, or use HGMD free version (3 years outdated).

#### Update

Updates should be done quarterly, timed with HGMD's releases.


