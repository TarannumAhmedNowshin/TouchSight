"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

/** Renders the tactile height map as a lit 3D surface, so sighted people can see the relief. */
export default function Relief({ heightmap }: { heightmap: string }) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ update: (b64: string) => void } | null>(null);

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xdfe3e9);
    const camera = new THREE.PerspectiveCamera(32, 297 / 210, 1, 2000);
    camera.position.set(0, -240, 285);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    // CPU displacement so normals (and therefore shading) follow the relief
    const SEG_X = 594, SEG_Y = 420, LIFT = 3.0;
    const geo = new THREE.PlaneGeometry(297, 210, SEG_X, SEG_Y);
    const count = geo.attributes.position.count;
    geo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(count * 3).fill(1), 3));
    const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, metalness: 0 });
    scene.add(new THREE.Mesh(geo, mat));
    scene.add(new THREE.HemisphereLight(0xffffff, 0xb8c0cf, 1.9));
    const sun = new THREE.DirectionalLight(0xffffff, 1.5);
    sun.position.set(-200, 160, 110); // low raking light makes raised lines cast shading
    scene.add(sun);

    const paper = new THREE.Color(0xf7f7f3), ink = new THREE.Color(0x1c2541);
    api.current = {
      update(b64) {
        const img = new Image();
        img.onload = () => {
          const cv = document.createElement("canvas");
          cv.width = SEG_X + 1;
          cv.height = SEG_Y + 1;
          const ctx = cv.getContext("2d", { willReadFrequently: true })!;
          ctx.drawImage(img, 0, 0, cv.width, cv.height);
          const px = ctx.getImageData(0, 0, cv.width, cv.height).data;
          const pos = geo.attributes.position as THREE.BufferAttribute;
          const col = geo.attributes.color as THREE.BufferAttribute;
          const c = new THREE.Color();
          for (let i = 0; i < count; i++) {
            const h = px[i * 4] / 255; // PlaneGeometry vertices run row by row from the top-left
            pos.setZ(i, h * LIFT);
            c.copy(paper).lerp(ink, Math.min(1, h * 1.4));
            col.setXYZ(i, c.r, c.g, c.b);
          }
          pos.needsUpdate = true;
          col.needsUpdate = true;
          geo.computeVertexNormals();
        };
        img.src = `data:image/png;base64,${b64}`;
      },
    };

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    let raf = 0;
    const loop = () => { controls.update(); renderer.render(scene, camera); raf = requestAnimationFrame(loop); };
    loop();
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      controls.dispose();
      geo.dispose();
      mat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  useEffect(() => { api.current?.update(heightmap); }, [heightmap]);

  return (
    <div className="relief" ref={host}>
      <p className="relief-hint">Drag to tilt. Scroll to zoom. Height is exaggerated so you can see the raised lines.</p>
    </div>
  );
}
