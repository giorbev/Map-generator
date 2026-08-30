from map_generator.application.use_cases.analyze_satmap_use_case import AnalyzeSatMapUseCase
from map_generator.domain.services.satmap_index_service import SatMapIndexService
from map_generator.infrastructure.adapters.pillow_resizer import PillowRgbAligner
from map_generator.infrastructure.normalization.percentile import Percentile99Normalizer


class SatMapFactory:
    @staticmethod
    def create_use_case() -> AnalyzeSatMapUseCase:
        normalizer = Percentile99Normalizer()
        index_service = SatMapIndexService(normalizer=normalizer)
        aligner = PillowRgbAligner()
        return AnalyzeSatMapUseCase(aligner=aligner, index_service=index_service)
