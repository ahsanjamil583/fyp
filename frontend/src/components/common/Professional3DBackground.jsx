import { useEffect, useRef } from "react";
import * as THREE from "three";

export function Professional3DBackground({ className = "", intensity = "hero" }) {
  const hostRef = useRef(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reduceMotion) return undefined;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera.position.set(0, 0, 8);

    const renderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      powerPreference: "high-performance",
      preserveDrawingBuffer: true,
    });
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.7));
    host.appendChild(renderer.domElement);

    const isAuth = intensity === "auth";
    const uniforms = {
      uTime: { value: 0 },
      uPointer: { value: new THREE.Vector2(0, 0) },
      uStrength: { value: isAuth ? 0.72 : 0.92 },
    };

    const wave = new THREE.Mesh(
      new THREE.PlaneGeometry(15, 9, 72, 42),
      new THREE.ShaderMaterial({
        transparent: true,
        depthWrite: false,
        uniforms,
        vertexShader: `
          uniform float uTime;
          uniform vec2 uPointer;
          uniform float uStrength;
          varying vec2 vUv;
          varying float vDepth;

          void main() {
            vUv = uv;
            vec3 pos = position;
            float ripple = sin(pos.x * 0.72 + uTime * 0.42) * 0.35;
            ripple += cos(pos.y * 0.95 + uTime * 0.3) * 0.24;
            ripple += sin((pos.x + pos.y) * 0.42 + uTime * 0.22) * 0.2;
            float pointerPull = 1.0 - smoothstep(0.0, 5.2, distance(pos.xy, uPointer * vec2(5.8, 3.2)));
            pos.z += (ripple + pointerPull * 0.72) * uStrength;
            pos.y += sin(pos.x * 0.34 + uTime * 0.18) * 0.12;
            vDepth = pos.z;
            gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
          }
        `,
        fragmentShader: `
          varying vec2 vUv;
          varying float vDepth;

          void main() {
            vec3 blackBlue = vec3(0.015, 0.035, 0.075);
            vec3 navy = vec3(0.025, 0.11, 0.24);
            vec3 cyan = vec3(0.07, 0.62, 0.85);
            float glow = smoothstep(-0.2, 1.0, vDepth);
            float edge = 1.0 - distance(vUv, vec2(0.5)) * 1.15;
            vec3 color = mix(blackBlue, navy, vUv.x + glow * 0.22);
            color = mix(color, cyan, max(glow - 0.35, 0.0) * 0.42);
            float alpha = clamp(0.28 + glow * 0.16 + edge * 0.08, 0.16, 0.52);
            gl_FragColor = vec4(color, alpha);
          }
        `,
      }),
    );
    wave.rotation.x = -0.74;
    wave.rotation.z = -0.09;
    scene.add(wave);

    const particleCount = isAuth ? 80 : 120;
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i += 1) {
      positions[i * 3] = (Math.random() - 0.5) * 13;
      positions[i * 3 + 1] = (Math.random() - 0.5) * 7;
      positions[i * 3 + 2] = (Math.random() - 0.5) * 2.8;
    }

    const particlesGeometry = new THREE.BufferGeometry();
    particlesGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const particles = new THREE.Points(
      particlesGeometry,
      new THREE.PointsMaterial({
        color: 0x55d6ff,
        size: isAuth ? 0.035 : 0.043,
        transparent: true,
        opacity: 0.28,
        depthWrite: false,
      }),
    );
    scene.add(particles);

    let width = 0;
    let height = 0;
    let frame = 0;
    let pointerX = 0;
    let pointerY = 0;
    let targetX = 0;
    let targetY = 0;
    const clock = new THREE.Clock();

    const resize = () => {
      const rect = host.getBoundingClientRect();
      width = Math.max(rect.width, 1);
      height = Math.max(rect.height, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const movePointer = (event) => {
      const rect = host.getBoundingClientRect();
      targetX = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      targetY = -(((event.clientY - rect.top) / rect.height - 0.5) * 2);
    };

    const animate = () => {
      const elapsed = clock.getElapsedTime();
      pointerX += (targetX - pointerX) * 0.055;
      pointerY += (targetY - pointerY) * 0.055;
      uniforms.uTime.value = elapsed;
      uniforms.uPointer.value.set(pointerX, pointerY);
      wave.rotation.y = pointerX * 0.055;
      wave.rotation.x = -0.74 + pointerY * 0.035;
      particles.rotation.y = elapsed * 0.018 + pointerX * 0.04;
      particles.rotation.x = pointerY * 0.025;
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(animate);
    };

    resize();
    animate();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", movePointer, { passive: true });

    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", movePointer);
      wave.geometry.dispose();
      wave.material.dispose();
      particlesGeometry.dispose();
      particles.material.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [intensity]);

  return (
    <div ref={hostRef} aria-hidden="true" className={`professional-3d-bg pointer-events-none absolute inset-0 ${className}`}>
      <div className="professional-3d-bg__fallback" />
      <div className="professional-3d-bg__vignette" />
    </div>
  );
}
