import * as THREE from 'three';
import { TilesRenderer } from '3d-tiles-renderer';
import {
  GoogleCloudAuthPlugin,
  ReorientationPlugin,
  TileCompressionPlugin,
  TilesFadePlugin,
  TileFlatteningPlugin,
  GLTFExtensionsPlugin,
  UpdateOnChangePlugin,
} from '3d-tiles-renderer/plugins';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { site, siteToWorld } from './coords';

/**
 * Google Photorealistic 3D Tiles around the site (only when VITE_GOOGLE_KEY is set).
 * The tileset is re-oriented so the plot origin sits at the world origin (ENU, +Y up), then nudged vertically
 * so the real street in front of the plot lines up with our y = 0. The plot itself is flattened so the old
 * buildings disappear under the new project.
 */
export class GoogleTiles {
  tiles: TilesRenderer;
  ready = false;
  private flatten: TileFlatteningPlugin;
  private aligned = false;
  private raycaster = new THREE.Raycaster();
  private holder = new THREE.Group();
  private frame = 0;
  attribution = '';

  constructor(private scene: THREE.Scene, private camera: THREE.PerspectiveCamera, renderer: THREE.WebGLRenderer, apiKey: string) {
    const tiles = new TilesRenderer();
    tiles.registerPlugin(new GoogleCloudAuthPlugin({ apiToken: apiKey, autoRefreshToken: true }));
    const draco = new DRACOLoader().setDecoderPath('https://www.gstatic.com/draco/versioned/decoders/1.5.7/');
    tiles.registerPlugin(new GLTFExtensionsPlugin({ dracoLoader: draco }));
    tiles.registerPlugin(new TileCompressionPlugin());
    tiles.registerPlugin(new TilesFadePlugin());
    tiles.registerPlugin(new UpdateOnChangePlugin());
    // approximate ellipsoidal height of the street (ASL + ~20 m geoid); corrected by raycast once loaded
    tiles.registerPlugin(
      new ReorientationPlugin({
        lat: THREE.MathUtils.degToRad(site.originLat),
        lon: THREE.MathUtils.degToRad(site.originLng),
        height: site.elevationAsl + 20,
        recenter: true,
      }),
    );
    this.flatten = new TileFlatteningPlugin();
    tiles.registerPlugin(this.flatten);
    tiles.setCamera(camera);
    tiles.setResolutionFromRenderer(camera, renderer);
    tiles.errorTarget = 6;
    tiles.group.name = 'GoogleTiles';
    // ReorientationPlugin yields an object frame with +X west and +Z north; the app uses +X east and -Z north,
    // so the tileset sits in a holder turned half a revolution about the up axis.
    this.holder.name = 'GoogleTilesHolder';
    this.holder.rotation.y = Math.PI;
    this.holder.add(tiles.group);
    this.holder.visible = false;
    scene.add(this.holder);
    this.tiles = tiles;
    tiles.addEventListener('load-tile-set', () => {
      this.ready = true;
    });
    // fine tiles near the site arrive after the root tileset; alignment keeps retrying until the street is hit
  }

  /** Flatten the plot (old buildings removed) once the tileset frame is known. */
  private addFlattenShapes() {
    const group = this.tiles.group;
    group.updateMatrixWorld(true);
    const inv = group.matrixWorld.clone().invert();
    const shape = (poly: Array<[number, number]>, h: number) => {
      const s = new THREE.Shape(poly.map(([x, y]) => new THREE.Vector2(x, y)));
      const geo = new THREE.ShapeGeometry(s);
      // ShapeGeometry is in the XY plane: map site (x, y) -> world, at height h
      const pos = geo.attributes.position as THREE.BufferAttribute;
      const v = new THREE.Vector3();
      for (let i = 0; i < pos.count; i++) {
        siteToWorld(pos.getX(i), pos.getY(i), h, v).applyMatrix4(inv);
        pos.setXYZ(i, v.x, v.y, v.z);
      }
      const mesh = new THREE.Mesh(geo);
      const up = new THREE.Vector3(0, 1, 0).transformDirection(inv);
      this.flatten.addShape(mesh, up.negate(), 80);
    };
    shape([[-3, -1], [84, -1], [86, 69], [-3, 70]], -0.4);
  }

  /** Raycast the real street in front of the plot and shift the tiles so it sits at y = 0. */
  private tryAlign() {
    const p = siteToWorld(40, -14, 300);
    this.raycaster.set(p, new THREE.Vector3(0, -1, 0));
    const hits = this.raycaster.intersectObject(this.tiles.group, true);
    if (hits.length) {
      this.holder.position.y -= hits[0].point.y;
      this.holder.updateMatrixWorld(true);
      this.aligned = true;
      this.addFlattenShapes();
    }
  }

  setVisible(v: boolean) {
    this.holder.visible = v;
  }

  update() {
    if (!this.holder.visible) return;
    this.camera.updateMatrixWorld();
    this.tiles.update();
    if (this.ready && !this.aligned && this.frame++ % 30 === 0) this.tryAlign();
    const attr = this.tiles.getAttributions?.() ?? [];
    this.attribution = attr.map((a: any) => (typeof a.value === 'string' ? a.value : '')).filter(Boolean).join(' · ');
  }
}
