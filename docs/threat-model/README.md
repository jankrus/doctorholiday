# docs/threat-model

System model (DFD), STRIDE analysis, attack tree (#7-#10).

- [system-model.md](system-model.md): scope, assumptions, DFD level 0 and 1, elements, data flows, trust boundaries, boundary-crossing flows (#7)
- [dfd-level0.mmd](dfd-level0.mmd), [dfd.mmd](dfd.mmd): DFD sources (Mermaid) with SVG/PNG exports
- [stride.md](stride.md): STRIDE analysis per element and boundary-crossing flow, 88 threats with mitigation, requirement and status (#8)
- [stride-selection.md](stride-selection.md): the three implemented STRIDE categories (S, E, I) with issues and verification, and the justification for T, R, D (#9)
- [attack-tree.md](attack-tree.md): worst-case attack tree (exfiltrate the health data of many patients) with countermeasures per leaf; source [attack-tree.mmd](attack-tree.mmd), exports SVG/PNG (#10)
