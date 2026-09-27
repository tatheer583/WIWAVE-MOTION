import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * A stylized 3D humanoid figure that represents a detected person.
 * Location targeting is simulated by moving the avatar along the Z axis 
 * based on the 'distance' prop (relative signal strength).
 * In multi-person mode, accepts a 'position' prop for explicit placement.
 */
const HumanSilhouette = ({ visible, distance, position }) => {
    const groupRef = useRef();

    useFrame((state) => {
        if (!groupRef.current) return;
        
        const time = state.clock.getElapsedTime();
        
        // Target opacity
        const targetOpacity = visible ? 0.7 : 0;
        
        // If explicit position is provided (multi-person mode), use it
        if (position) {
            groupRef.current.position.x = THREE.MathUtils.lerp(groupRef.current.position.x, position[0], 0.05);
            groupRef.current.position.z = THREE.MathUtils.lerp(groupRef.current.position.z, position[2], 0.05);
        } else {
            // Single-person mode: Target Position based on estimated distance (0 to 10)
            // We'll map distance 5.0 (center) to z=0, 0.0 to z=-8, and 10.0 to z=8
            const targetZ = (distance - 5.0) * 1.5;
            groupRef.current.position.z = THREE.MathUtils.lerp(groupRef.current.position.z, targetZ, 0.05);
        }

        // Breathing/Floating animation
        const hover = Math.sin(time * 2) * 0.1;
        groupRef.current.position.y = hover;

        // Apply opacity to all parts
        groupRef.current.traverse((child) => {
            if (child.isMesh) {
                child.material.opacity = THREE.MathUtils.lerp(child.material.opacity, targetOpacity, 0.1);
            }
        });
    });

    const glowColor = "#00ffcc";

    return (
        <group ref={groupRef} position={[0, 0, 0]}>
            {/* Head */}
            <mesh position={[0, 1.8, 0]}>
                <sphereGeometry args={[0.25, 32, 32]} />
                <meshBasicMaterial color={glowColor} transparent opacity={0} blending={THREE.AdditiveBlending} />
            </mesh>

            {/* Torso */}
            <mesh position={[0, 1.1, 0]}>
                <cylinderGeometry args={[0.3, 0.2, 1, 32]} />
                <meshBasicMaterial color={glowColor} transparent opacity={0} blending={THREE.AdditiveBlending} />
            </mesh>

            {/* Left Arm */}
            <mesh position={[-0.5, 1.2, 0]} rotation={[0, 0, Math.PI / 6]}>
                <cylinderGeometry args={[0.1, 0.08, 0.8, 16]} />
                <meshBasicMaterial color={glowColor} transparent opacity={0} blending={THREE.AdditiveBlending} />
            </mesh>

            {/* Right Arm */}
            <mesh position={[0.5, 1.2, 0]} rotation={[0, 0, -Math.PI / 6]}>
                <cylinderGeometry args={[0.1, 0.08, 0.8, 16]} />
                <meshBasicMaterial color={glowColor} transparent opacity={0} blending={THREE.AdditiveBlending} />
            </mesh>

            {/* Left Leg */}
            <mesh position={[-0.2, 0.3, 0]}>
                <cylinderGeometry args={[0.12, 0.1, 0.7, 16]} />
                <meshBasicMaterial color={glowColor} transparent opacity={0} blending={THREE.AdditiveBlending} />
            </mesh>

            {/* Right Leg */}
            <mesh position={[0.2, 0.3, 0]}>
                <cylinderGeometry args={[0.12, 0.1, 0.7, 16]} />
                <meshBasicMaterial color={glowColor} transparent opacity={0} blending={THREE.AdditiveBlending} />
            </mesh>

            {/* Base Aura */}
            <mesh position={[0, -0.9, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <ringGeometry args={[0.5, 1.5, 32]} />
                <meshBasicMaterial color={glowColor} transparent opacity={0} blending={THREE.AdditiveBlending} />
            </mesh>
        </group>
    );
};

export default HumanSilhouette;
