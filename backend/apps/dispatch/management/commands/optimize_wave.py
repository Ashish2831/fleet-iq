from django.core.management.base import BaseCommand

from apps.dispatch.solver import solve_wave
from apps.telemetry.geo import haversine_m


class Command(BaseCommand):
    help = "Toy CVRP on a 5-stop matrix (greedy stand-in for OR-Tools RoutingModel)."

    def handle(self, *args, **opts):
        # Depot + 4 drops around Whitefield
        pts = [
            (12.9698, 77.7499),
            (12.9716, 77.7500),
            (12.9732, 77.7110),
            (12.9784, 77.6408),
            (12.9352, 77.6245),
        ]
        n = len(pts)
        matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                matrix[i][j] = haversine_m(pts[i][0], pts[i][1], pts[j][0], pts[j][1]) / 1000.0
        demands = [0, 200, 150, 80, 120]
        capacities = [500, 400]
        result = solve_wave(matrix, demands, capacities)
        self.stdout.write(str(result))
