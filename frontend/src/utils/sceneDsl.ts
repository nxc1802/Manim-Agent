import type {
  DslAnimationStep,
  DslCameraState,
  DslPosition,
  DslTheme,
  DslTransition,
  DslVisualElement,
  JsonValue,
  SceneDsl,
  SceneDslBeat,
} from '../types/api';

export const pythonLiteral = (value: JsonValue): string => {
  if (value === null) return 'None';
  if (typeof value === 'boolean') return value ? 'True' : 'False';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '0.0';
  if (Array.isArray(value)) return `[${value.map(pythonLiteral).join(', ')}]`;
  return `{${Object.entries(value)
    .map(([key, item]) => `${JSON.stringify(key)}: ${pythonLiteral(item)}`)
    .join(', ')}}`;
};

const formatPosition = (position: DslPosition | null): string => position
  ? `Position(x=${position.x}, y=${position.y}, z=${position.z}, relative_to=${pythonLiteral(position.relative_to)}, target_id=${pythonLiteral(position.target_id)}, buff=${position.buff})`
  : 'None';

const formatTheme = (theme: DslTheme | null): string => theme
  ? `ThemeConfig(primary_color=${pythonLiteral(theme.primary_color)}, secondary_color=${pythonLiteral(theme.secondary_color)}, background_color=${pythonLiteral(theme.background_color)}, font=${pythonLiteral(theme.font)})`
  : 'None';

const formatCamera = (camera: DslCameraState | null): string => camera
  ? `CameraState(position=${pythonLiteral(camera.position)}, zoom=${pythonLiteral(camera.zoom)})`
  : 'None';

const formatTransition = (transition: DslTransition | null): string => transition
  ? `TransitionSpec(transition_type=${pythonLiteral(transition.transition_type)}, duration=${transition.duration})`
  : 'None';

const formatVisualElement = (element: DslVisualElement): string => `VisualElement(
                    id=${pythonLiteral(element.id)},
                    type=${pythonLiteral(element.type)},
                    params=${pythonLiteral(element.params)},
                    position=${formatPosition(element.position)}
                )`;

const formatAnimation = (animation: DslAnimationStep): string => `AnimationStep(
                    target_ids=${pythonLiteral(animation.target_ids)},
                    animation_type=${pythonLiteral(animation.animation_type)},
                    params=${pythonLiteral(animation.params)},
                    run_time=${pythonLiteral(animation.run_time)},
                    simultaneous=${pythonLiteral(animation.simultaneous)}
                )`;

const formatBeat = (beat: SceneDslBeat): string => `SceneDSLBeat(
            id=${pythonLiteral(beat.id)},
            label=${pythonLiteral(beat.label)},
            duration_seconds=${beat.duration_seconds},
            narration=${pythonLiteral(beat.narration)},
            visual_elements=[
${beat.visual_elements.map(formatVisualElement).map((item) => `                ${item}`).join(',\n')}
            ],
            animations=[
${beat.animations.map(formatAnimation).map((item) => `                ${item}`).join(',\n')}
            ],
            camera=${formatCamera(beat.camera)},
            transition_out=${formatTransition(beat.transition_out)}
        )`;

export const formatDslToPython = (dsl: SceneDsl): string => `from shared.schemas.scene_dsl import SceneDSLBeat, VisualElement, AnimationStep, Position, ThemeConfig, CameraState, TransitionSpec

class GeneratedSceneDSL:
    version = ${pythonLiteral(dsl.version)}
    title = ${pythonLiteral(dsl.title)}
    global_theme = ${formatTheme(dsl.global_theme)}
    metadata = ${pythonLiteral(dsl.metadata)}
    beats = [
${dsl.beats.map(formatBeat).map((item) => `        ${item}`).join(',\n')}
    ]
`;
