- [ ] Bump the version and sha key in https://gitlab.com/alleles/ella-anno/-/blob/dev/ops/install_thirdparty.py
- [ ] `make build && build-annobuilder`
- [ ] run `make generate-amg-package PKG_NAME=vep` command 
- [ ] upload to DO (`make upload-package ..`)
- [ ] test (`make test` on focus)
- [ ] CI tests pass
- [ ] re-analysis in ELLA-stage
- [ ] eyeball the output vcf for sanity