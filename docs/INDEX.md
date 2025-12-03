# Documentation Index

## Current Documentation (December 2025)

### Main Documents

1. **[README.md](../README.md)** - Project overview
   - Quick start guide
   - All three applications overview
   - Installation instructions
   - Basic workflow examples

2. **[applications.md](applications.md)** - Complete application guides
   - Frame Exporter detailed documentation
   - Viewer/Annotator detailed documentation
   - Annotation Checker detailed documentation
   - Workflows and keyboard shortcuts
   - Troubleshooting guides
   - German UI reference

3. **[architecture.md](architecture.md)** - System design
   - Technology stack
   - Module structure
   - Data flow diagrams
   - Design patterns
   - Configuration and state management
   - Performance considerations

4. **[yolo-training-structure.md](yolo-training-structure.md)** - Training dataset organization
   - 73-bucket structure specification
   - Numeric prefix mapping
   - YOLO class definitions
   - Filename conventions
   - Bucket balance guidelines
   - CSV annotation logging

5. **[coding-guidelines.md](coding-guidelines.md)** - Development standards
   - Python conventions
   - Type hints requirements
   - Code style
   - Error handling patterns

6. **[fieldtest-learnings.md](fieldtest-learnings.md)** - Field deployment insights
   - Jetson Orin Nano + ZED2i setup
   - LOSSLESS mode requirements
   - Storage recommendations
   - Field test lessons

## Archived Documents

Located in `archive/` directory:
- `status.md` - Old project status (replaced by current README)
- `viewer-annotator-plan.md` - Planning document (implemented)
- `frame-export.md` - Export planning (now in applications.md)
- `output-root.md` - Output path planning (now in architecture.md)
- `architecture.md.old` - Previous architecture draft

## Documentation Philosophy

### Distinct Purpose per Document
- **README**: Quick start, overview, navigation to detailed docs
- **applications.md**: User-facing feature documentation
- **architecture.md**: Developer-facing design documentation
- **yolo-training-structure.md**: Dataset organization specification
- **coding-guidelines.md**: Development conventions
- **fieldtest-learnings.md**: Deployment context

### Cross-References
Documents reference each other to avoid duplication:
- README links to all detailed docs
- applications.md references yolo-training-structure.md for bucket details
- architecture.md references applications.md for usage patterns
- Copilot instructions (.github/) reference all docs for context

### Update Strategy
When code changes:
1. Update relevant application doc (applications.md) if user-facing feature changes
2. Update architecture doc if design pattern or data flow changes
3. Update yolo-training-structure.md if bucket organization changes
4. Update README if new application added or workflow changes
5. Keep copilot instructions synchronized with critical patterns

## Quick Navigation

### For Users
- **Getting started**: [README.md](../README.md)
- **Using Frame Exporter**: [applications.md#frame-exporter](applications.md#1-frame-exporter-gui_apppy)
- **Using Viewer/Annotator**: [applications.md#viewer-annotator](applications.md#2-viewerannotator-viewer_apppy)
- **Using Annotation Checker**: [applications.md#annotation-checker](applications.md#3-annotation-checker-checker_apppy)
- **Understanding buckets**: [yolo-training-structure.md](yolo-training-structure.md)

### For Developers
- **System design**: [architecture.md](architecture.md)
- **Code conventions**: [coding-guidelines.md](coding-guidelines.md)
- **Module responsibilities**: [architecture.md#module-structure](architecture.md#module-structure)
- **Data flow**: [architecture.md#data-flow](architecture.md#data-flow)
- **Design patterns**: [architecture.md#key-design-patterns](architecture.md#key-design-patterns)

### For AI Assistants (Copilot)
- **Quick reference**: [../.github/copilot-instructions.md](../.github/copilot-instructions.md)
- **Critical patterns**: Copilot instructions + architecture.md
- **Implementation examples**: All documents contain code snippets

## Documentation Completeness

### ✅ Well Documented
- [x] All three applications
- [x] YOLO training structure
- [x] Export-only workflow
- [x] CSRT tracking integration
- [x] Bbox persistence patterns
- [x] Duplicate detection
- [x] Zoom/pan implementation
- [x] Keyboard shortcuts
- [x] German UI reference

### 🚧 Could Be Expanded
- [ ] Testing strategy (tests/ currently empty)
- [ ] Deployment automation scripts
- [ ] Data augmentation pipeline
- [ ] Model training integration
- [ ] Performance benchmarks
- [ ] Video tutorials/screenshots

### 📝 Future Documentation
- [ ] API reference (if exposing programmatic interface)
- [ ] Plugin development guide (if extensibility added)
- [ ] Cloud integration guide (if remote storage added)
- [ ] Multi-user annotation guide (if collaboration added)

## Maintenance Notes

### Last Major Update
December 2, 2025 - Complete documentation restructure:
- Created comprehensive applications.md (19KB)
- Created yolo-training-structure.md (17KB) 
- Rewrote architecture.md (15KB)
- Updated README.md with current state
- Streamlined copilot-instructions.md
- Archived outdated planning docs

### Update Frequency
- **After each feature**: Update applications.md
- **After architecture change**: Update architecture.md
- **After bucket change**: Update yolo-training-structure.md
- **Before each release**: Review all docs for accuracy

### Quality Checklist
Before committing documentation changes:
- [ ] All code snippets tested and verified
- [ ] Cross-references still valid
- [ ] No contradictions between documents
- [ ] German UI labels match implementation
- [ ] File paths and commands tested
- [ ] Screenshots current (if applicable)
