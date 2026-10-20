import numpy as np


class OODDetector:
    def assess(self, query, groups):
        reasons=[]
        for name, stats in groups.items():
            for column, low, high in zip(stats['features'], stats['min'], stats['max']):
                value=float(query[column])
                if value < float(low) or value > float(high):
                    reasons.append(f'{column}={value:.3g} outside 2023 reference range [{float(low):.3g}, {float(high):.3g}]')
        return bool(reasons), reasons
