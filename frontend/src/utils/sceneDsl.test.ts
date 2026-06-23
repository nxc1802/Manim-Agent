import { describe, expect, it } from 'vitest';

import type { SceneDsl } from '../types/api';
import { formatDslToPython, pythonLiteral } from './sceneDsl';

describe('scene DSL serializer', () => {
  it('uses Python literals instead of JSON literals', () => {
    expect(pythonLiteral({ enabled: true, value: null })).toBe(
      '{"enabled": True, "value": None}',
    );
  });

  it('preserves all structured scene fields', () => {
    const dsl: SceneDsl = {
      version: '1.0',
      title: 'Round trip',
      global_theme: {
        primary_color: 'BLUE',
        secondary_color: 'GREEN',
        background_color: 'BLACK',
        font: null,
      },
      metadata: { reviewed: true },
      beats: [{
        id: 'beat_1',
        label: 'Intro',
        duration_seconds: 2,
        narration: null,
        visual_elements: [],
        animations: [],
        camera: { position: [0, 1, 0], zoom: 1.5 },
        transition_out: { transition_type: 'fade_out', duration: 0.5 },
      }],
    };

    const source = formatDslToPython(dsl);
    expect(source).toContain('metadata = {"reviewed": True}');
    expect(source).toContain('font=None');
    expect(source).toContain('CameraState(position=[0, 1, 0], zoom=1.5)');
    expect(source).toContain('TransitionSpec(transition_type="fade_out", duration=0.5)');
  });
});
