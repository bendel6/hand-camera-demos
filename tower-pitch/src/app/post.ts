import * as THREE from 'three';
import {
  BloomEffect,
  BlendFunction,
  Effect,
  EffectComposer,
  EffectPass,
  OutlineEffect,
  RenderPass,
  SMAAEffect,
  SMAAPreset,
  ToneMappingEffect,
  ToneMappingMode,
  VignetteEffect,
  DepthOfFieldEffect,
} from 'postprocessing';
import { N8AOPostPass } from 'n8ao';

/** Exposure + subtle colour grade (lift/gain, saturation), applied in linear HDR before tone mapping. */
class GradeEffect extends Effect {
  constructor() {
    super(
      'GradeEffect',
      /* glsl */ `
      uniform float exposure;
      uniform float saturation;
      uniform vec3 tint;
      void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
        vec3 c = inputColor.rgb * exposure * tint;
        float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
        c = mix(vec3(l), c, saturation);
        outputColor = vec4(c, inputColor.a);
      }`,
      {
        uniforms: new Map<string, THREE.Uniform>([
          ['exposure', new THREE.Uniform(1.0)],
          ['saturation', new THREE.Uniform(1.12)],
          ['tint', new THREE.Uniform(new THREE.Color(1, 1, 1))],
        ]),
      },
    );
  }
  set exposure(v: number) {
    this.uniforms.get('exposure')!.value = v;
  }
  get exposure() {
    return this.uniforms.get('exposure')!.value;
  }
}

export class Post {
  composer: EffectComposer;
  ao: N8AOPostPass;
  bloom: BloomEffect;
  grade: GradeEffect;
  outline: OutlineEffect;
  dof: DepthOfFieldEffect;
  private dofPass: EffectPass;

  constructor(renderer: THREE.WebGLRenderer, scene: THREE.Scene, camera: THREE.PerspectiveCamera) {
    this.composer = new EffectComposer(renderer, { frameBufferType: THREE.HalfFloatType, multisampling: 0 });
    this.composer.addPass(new RenderPass(scene, camera));
    const w = renderer.domElement.width;
    const h = renderer.domElement.height;
    this.ao = new N8AOPostPass(scene, camera, w, h);
    this.ao.configuration.aoRadius = 2.6;
    this.ao.configuration.distanceFalloff = 1.2;
    this.ao.configuration.intensity = 1.5;
    this.ao.configuration.gammaCorrection = false;
    this.ao.configuration.halfRes = false;
    this.ao.configuration.depthAwareUpsampling = true;
    this.ao.setQualityMode('High');
    this.composer.addPass(this.ao);

    this.outline = new OutlineEffect(scene, camera, {
      blendFunction: BlendFunction.SCREEN,
      edgeStrength: 3.0,
      pulseSpeed: 0.0,
      visibleEdgeColor: 0xffb37a,
      hiddenEdgeColor: 0x6a4630,
      blur: true,
      xRay: true,
    });
    this.bloom = new BloomEffect({
      mipmapBlur: true,
      intensity: 0.55,
      luminanceThreshold: 1.1,
      luminanceSmoothing: 0.25,
      radius: 0.72,
    });
    this.grade = new GradeEffect();
    const tone = new ToneMappingEffect({ mode: ToneMappingMode.AGX });
    const vignette = new VignetteEffect({ offset: 0.32, darkness: 0.42 });
    this.dof = new DepthOfFieldEffect(camera, { focusDistance: 0.0, focalLength: 0.05, bokehScale: 0.0 });
    this.dofPass = new EffectPass(camera, this.dof);
    this.dofPass.enabled = false;
    this.composer.addPass(this.dofPass);
    this.composer.addPass(new EffectPass(camera, this.outline, this.bloom, this.grade));
    this.composer.addPass(new EffectPass(camera, tone, vignette));
    const finalPass = new EffectPass(camera, new SMAAEffect({ preset: SMAAPreset.ULTRA }));
    finalPass.dithering = true;
    this.composer.addPass(finalPass);
  }

  setSize(w: number, h: number) {
    this.composer.setSize(w, h);
  }

  setDof(on: boolean, focusWorldDist = 200) {
    this.dofPass.enabled = on;
    if (on) {
      this.dof.cocMaterial.worldFocusDistance = focusWorldDist;
      this.dof.cocMaterial.worldFocusRange = focusWorldDist * 0.6;
      this.dof.bokehScale = 2.2;
    }
  }

  render(dt: number) {
    this.composer.render(dt);
  }
}
