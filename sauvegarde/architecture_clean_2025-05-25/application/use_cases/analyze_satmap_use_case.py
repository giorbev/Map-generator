from map_generator.domain.models.satmap import SatMapInput, SatMapIndices
from map_generator.domain.services.satmap_index_service import SatMapIndexService


class AnalyzeSatMapUseCase:
    def __init__(self, aligner, index_service: SatMapIndexService):
        self._aligner = aligner
        self._index_service = index_service

    def align(self, payload: SatMapInput):
        return self._aligner.align(payload.rgb, payload.target_shape)

    def execute_from_aligned(self, aligned_rgb, report) -> SatMapIndices:
        return self._index_service.compute(aligned_rgb, report)

    def execute(self, payload: SatMapInput) -> SatMapIndices:
        aligned_rgb, report = self.align(payload)
        return self.execute_from_aligned(aligned_rgb, report)
