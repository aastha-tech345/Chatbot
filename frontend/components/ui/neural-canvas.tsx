"use client";
/**
 * NeuralCanvas — lightweight Three.js particle-network animation.
 * Dynamically imported so Three.js never enters the main bundle.
 * Fully cleaned up on unmount.
 */
import { useEffect, useRef } from "react";

const NODE_COUNT = 38;
const MAX_DIST   = 0.28;
const SPEED      = 0.00018;

export function NeuralCanvas({ className }: { className?: string }) {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    let animId: number;
    let disposed = false;

    import("three").then((THREE) => {
      if (disposed) return;
      const el = mountRef.current;
      if (!el) return;

      const W = el.clientWidth  || 480;
      const H = el.clientHeight || 480;

      /* ── Renderer ── */
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
      renderer.setSize(W, H);
      renderer.setClearColor(0x000000, 0);
      el.appendChild(renderer.domElement);

      /* ── Scene / Camera ── */
      const scene  = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
      camera.position.z = 1;

      /* ── Nodes ── */
      type Node = { x: number; y: number; vx: number; vy: number };
      const nodes: Node[] = Array.from({ length: NODE_COUNT }, () => ({
        x:  Math.random() * 2 - 1,
        y:  Math.random() * 2 - 1,
        vx: (Math.random() - 0.5) * SPEED * 2,
        vy: (Math.random() - 0.5) * SPEED * 2,
      }));

      /* ── Node dots ── */
      const dotGeo = new THREE.CircleGeometry(0.007, 8);
      const dotMat = new THREE.MeshBasicMaterial({
        color: 0x7c3aed, transparent: true, opacity: 0.55,
      });
      const dots = nodes.map(() => {
        const mesh = new THREE.Mesh(dotGeo, dotMat.clone());
        scene.add(mesh);
        return mesh;
      });

      /* ── Lines (pre-allocated buffer) ── */
      const MAX_SEGS = NODE_COUNT * NODE_COUNT;
      const positions = new Float32Array(MAX_SEGS * 6);
      const lineGeo   = new THREE.BufferGeometry();
      lineGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      lineGeo.setDrawRange(0, 0);
      const lineMaterial = new THREE.LineBasicMaterial({
        color: 0x7c3aed, transparent: true, opacity: 0.18,
      });
      const lineSegs = new THREE.LineSegments(lineGeo, lineMaterial);
      scene.add(lineSegs);

      /* ── Resize ── */
      const onResize = () => {
        const w = el.clientWidth  || 480;
        const h = el.clientHeight || 480;
        renderer.setSize(w, h);
      };
      window.addEventListener("resize", onResize);

      /* ── Loop ── */
      function animate() {
        animId = requestAnimationFrame(animate);
        let segCount = 0;

        for (let i = 0; i < nodes.length; i++) {
          const n = nodes[i];
          n.x += n.vx;  n.y += n.vy;
          if (n.x > 1 || n.x < -1) n.vx *= -1;
          if (n.y > 1 || n.y < -1) n.vy *= -1;
          dots[i].position.set(n.x, n.y, 0);

          for (let j = i + 1; j < nodes.length; j++) {
            const m  = nodes[j];
            const dx = n.x - m.x, dy = n.y - m.y;
            if (dx * dx + dy * dy < MAX_DIST * MAX_DIST) {
              const b = segCount * 6;
              positions[b]   = n.x; positions[b+1] = n.y; positions[b+2] = 0;
              positions[b+3] = m.x; positions[b+4] = m.y; positions[b+5] = 0;
              segCount++;
            }
          }
        }

        lineGeo.attributes.position.needsUpdate = true;
        lineGeo.setDrawRange(0, segCount * 2);
        renderer.render(scene, camera);
      }

      animate();

      /* ── Cleanup captured in closure ── */
      const doCleanup = () => {
        cancelAnimationFrame(animId);
        window.removeEventListener("resize", onResize);
        dotGeo.dispose();
        dotMat.dispose();
        dots.forEach((d) => (d.material as typeof dotMat).dispose());
        lineGeo.dispose();
        lineMaterial.dispose();
        renderer.dispose();
        if (el.contains(renderer.domElement)) el.removeChild(renderer.domElement);
      };

      // Store cleanup so the outer return can call it
      (el as HTMLDivElement & { __threeCleanup?: () => void }).__threeCleanup = doCleanup;
    });

    return () => {
      disposed = true;
      cancelAnimationFrame(animId);
      const el = mountRef.current as (HTMLDivElement & { __threeCleanup?: () => void }) | null;
      el?.__threeCleanup?.();
    };
  }, []);

  return <div ref={mountRef} className={className} aria-hidden="true" />;
}
