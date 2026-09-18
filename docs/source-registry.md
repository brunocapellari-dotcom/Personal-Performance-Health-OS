# Source Registry — Nutrition, Activity and Evidence

Every source adapter must retain source ID, version/retrieval date, license/use notes, raw hash when possible and canonical nutrient/unit mapping.

## Nutrition

### TACO / NEPA-UNICAMP
Role: Brazilian reference food composition data. Prefer original official spreadsheet/PDF as canonical input. Preserve edition and row identity.

### TBCA
Role: broad Brazilian food composition and household-measure reference. Treat website data as a distinct source from TACO; never silently merge values.

### USDA FoodData Central
Role: high-coverage reference foods and branded foods where appropriate. Keep FDC identifiers and source types.

### Open Food Facts
Role: packaged-product/barcode data. Use current API and preserve ODbL attribution/source metadata. Crowd-sourced values require quality flags.

## Activity / Wearables

### Android Health Connect
Role: preferred Android aggregation layer for supported apps/devices. Preserve originating data-source metadata rather than labeling everything simply as `Health Connect`.

### FIT
Role: file import for wearable/sport activities. Keep original file hash and parser version.

### GPX
Role: route/location import. Keep original file hash; derived distance/elevation are recomputable projections.

## Knowledge

Research AI obtains ACSM, NSCA, TSAC-F, H2F, sport guidelines, systematic reviews, meta-analyses, peer-reviewed papers and technical books. Knowledge Factory/Segundo Cérebro validates claims. Health OS stores evidence references used in material decisions.
