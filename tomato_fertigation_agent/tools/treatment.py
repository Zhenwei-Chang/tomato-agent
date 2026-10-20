from .base import Outcome


def get_treatment_recipe(data, args):
    result = data.recipe(args.treatment_id)
    warnings = ['CK K2SO4 is a derived plan fill, not a direct observed value'] if args.treatment_id == 'CK' else []
    return Outcome(result, 'treatment', warnings=warnings,
                   evidence=[data.evidence('data/processed/treatments_canonical.csv', args.treatment_id), data.evidence('docs/DATA_LINEAGE.md','treatments')],
                   confidence='MEDIUM', reasons=['Recipe provenance distinguished from nutrient calculations'],
                   limitations=['Recipe concentrations are not irrigation/fertilization event doses'])
