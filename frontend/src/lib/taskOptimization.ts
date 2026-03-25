type RoutePointLike = {
  latitude: number;
  longitude: number;
  radius_m: number;
};

type XYPoint = {
  x: number;
  y: number;
};

type LegMetric = {
  index: number;
  centerDistanceKm: number;
  optimizedDistanceKm: number;
  midpoint: [number, number];
};

function toRadians(degrees: number): number {
  return (degrees * Math.PI) / 180;
}

function toDegrees(radians: number): number {
  return (radians * 180) / Math.PI;
}

export function haversineKm(from: { latitude: number; longitude: number }, to: { latitude: number; longitude: number }): number {
  const earthRadiusKm = 6371;
  const deltaLat = toRadians(to.latitude - from.latitude);
  const deltaLon = toRadians(to.longitude - from.longitude);
  const fromLat = toRadians(from.latitude);
  const toLat = toRadians(to.latitude);
  const a = Math.sin(deltaLat / 2) ** 2 + Math.cos(fromLat) * Math.cos(toLat) * Math.sin(deltaLon / 2) ** 2;
  return 2 * earthRadiusKm * Math.asin(Math.sqrt(a));
}

function distance(a: XYPoint, b: XYPoint): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function moveToward(from: XYPoint, to: XYPoint, distanceKm: number): XYPoint {
  const total = distance(from, to);
  if (!total || distanceKm <= 0) {
    return from;
  }
  const ratio = Math.min(1, distanceKm / total);
  return {
    x: from.x + (to.x - from.x) * ratio,
    y: from.y + (to.y - from.y) * ratio,
  };
}

function closestPointOnSegment(target: XYPoint, segmentStart: XYPoint, segmentEnd: XYPoint): XYPoint {
  const dx = segmentEnd.x - segmentStart.x;
  const dy = segmentEnd.y - segmentStart.y;
  const lengthSquared = dx * dx + dy * dy;
  if (!lengthSquared) {
    return segmentStart;
  }
  const projection = ((target.x - segmentStart.x) * dx + (target.y - segmentStart.y) * dy) / lengthSquared;
  const t = Math.max(0, Math.min(1, projection));
  return {
    x: segmentStart.x + dx * t,
    y: segmentStart.y + dy * t,
  };
}

function projectInsideCircle(center: XYPoint, radiusKm: number, target: XYPoint): XYPoint {
  const targetDistance = distance(center, target);
  if (targetDistance <= radiusKm) {
    return target;
  }
  return moveToward(center, target, radiusKm);
}

function toXY(referenceLatitude: number, referenceLongitude: number, point: RoutePointLike): XYPoint {
  const latScaleKm = 111.32;
  const lonScaleKm = Math.cos(toRadians(referenceLatitude)) * 111.32;
  return {
    x: (point.longitude - referenceLongitude) * lonScaleKm,
    y: (point.latitude - referenceLatitude) * latScaleKm,
  };
}

function toLngLat(referenceLatitude: number, referenceLongitude: number, point: XYPoint): [number, number] {
  const latScaleKm = 111.32;
  const lonScaleKm = Math.cos(toRadians(referenceLatitude)) * 111.32;
  return [
    referenceLongitude + point.x / lonScaleKm,
    referenceLatitude + point.y / latScaleKm,
  ];
}

export function computeTaskOptimization(points: RoutePointLike[]) {
  if (!points.length) {
    return { totalDistanceKm: 0, optimizedDistanceKm: 0, routeCoordinates: [] as [number, number][], legMetrics: [] as LegMetric[] };
  }

  if (points.length === 1) {
    return {
      totalDistanceKm: 0,
      optimizedDistanceKm: 0,
      routeCoordinates: [[points[0].longitude, points[0].latitude]] as [number, number][],
      legMetrics: [] as LegMetric[],
    };
  }

  const referenceLatitude = points.reduce((sum, point) => sum + point.latitude, 0) / points.length;
  const referenceLongitude = points.reduce((sum, point) => sum + point.longitude, 0) / points.length;
  const centers = points.map((point) => toXY(referenceLatitude, referenceLongitude, point));
  const radiiKm = points.map((point) => Math.max(0, point.radius_m / 1000));
  const optimized = centers.map((center) => ({ ...center }));

  for (let iteration = 0; iteration < 14; iteration += 1) {
    let prevTotal = 0;
    for (let i = 1; i < optimized.length; i += 1) {
      prevTotal += distance(optimized[i - 1], optimized[i]);
    }
    for (let index = 0; index < centers.length; index += 1) {
      const center = centers[index];
      const radiusKm = radiiKm[index];
      if (index === 0) {
        optimized[index] = projectInsideCircle(center, radiusKm, optimized[index + 1]);
        continue;
      }
      if (index === centers.length - 1) {
        optimized[index] = projectInsideCircle(center, radiusKm, optimized[index - 1]);
        continue;
      }
      const candidate = closestPointOnSegment(center, optimized[index - 1], optimized[index + 1]);
      optimized[index] = projectInsideCircle(center, radiusKm, candidate);
    }
    let newTotal = 0;
    for (let i = 1; i < optimized.length; i += 1) {
      newTotal += distance(optimized[i - 1], optimized[i]);
    }
    if (Math.abs(newTotal - prevTotal) < 0.001) break;
  }

  let totalDistanceKm = 0;
  let optimizedDistanceKm = 0;
  const legMetrics: LegMetric[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const centerDistanceKm = haversineKm(points[index - 1], points[index]);
    const optimizedLegDistanceKm = distance(optimized[index - 1], optimized[index]);
    totalDistanceKm += centerDistanceKm;
    optimizedDistanceKm += optimizedLegDistanceKm;
    legMetrics.push({
      index,
      centerDistanceKm,
      optimizedDistanceKm: optimizedLegDistanceKm,
      midpoint: toLngLat(referenceLatitude, referenceLongitude, {
        x: (optimized[index - 1].x + optimized[index].x) / 2,
        y: (optimized[index - 1].y + optimized[index].y) / 2,
      }),
    });
  }

  return {
    totalDistanceKm,
    optimizedDistanceKm,
    routeCoordinates: optimized.map((point) => toLngLat(referenceLatitude, referenceLongitude, point)),
    legMetrics,
  };
}
