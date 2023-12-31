<div align="center">
  <a href="http://allel.es">
    <img width="350px" height="200px" src="https://gitlab.com/alleles/ella-anno/raw/dev/docs/logo_anno_blue.svg"/>
  </a>
</div>

ELLA anno is the annotation service for the genetic variant interpretation tool [ELLA](http://allel.es). It takes annotation data from several sources (gnomAD, ClinVar and VEP by default, but you can also add others) and uses [vcfanno](https://github.com/brentp/vcfanno) to create annotated VCFs. You can then use [ella-anno-target](https://gitlab.com/alleles/ella-anno-target) to prepare additional, ELLA-specific files so that it can be easily imported for interpretation.

### Setup

For details on how to setup and run the ELLA annotation service, please see the [technical documentation](http://allel.es/anno-docs/technical/setup.html).

### Documentation

Documentation in the /docs folder is available at [allel.es](http://allel.es/anno-docs), but can also be built using [Vuepress](https://vuepress.vuejs.org/). 

### Contact

For support and suggestions, please contact [ella-support](ma&#105;lt&#111;&#58;&#101;%6&#67;la&#37;2&#68;s&#117;pport&#64;m&#101;&#100;i&#115;&#105;&#110;&#46;%75i%&#54;F&#46;n%&#54;F).

### License and copyright

ELLA anno  
Copyright (C) 2020-2023 ELLA contributors

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.