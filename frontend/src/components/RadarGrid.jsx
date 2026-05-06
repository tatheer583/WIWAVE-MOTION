import { useRef, useMemo } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

/**
 * A 3D wireframe grid that ripples based on signal variance.
 */
const RadarGrid = ({ variance }) => {
    const meshRef = useRef();
    const size = 20;
    const divisions = 40;

    // We'll use a custom shader or modify geometry to create ripples.
    // For simplicity and performance, we'll displace vertices in the useFrame.
    
    const initialPositions = useMemo(() => {
        const geo = new THREE.PlaneGeometry(size, size, divisions, divisions);
        return geo.attributes.position.array.slice();
    }, []);

    useFrame((state) => {
        if (!meshRef.current) return;
        
        const time = state.clock.getElapsedTime();
        const positions = meshRef.current.geometry.attributes.position.array;
        
        // Intensity of the ripple scales with variance
        const rippleIntensity = Math.max(0.05, variance * 0.1);
        const rippleSpeed = 2 + variance * 0.5;

        for (let i = 0; i < positions.length; i += 3) {
            const x = initialPositions[i];
            const y = initialPositions[i + 1];
            
            // Distance from center
            const d = Math.sqrt(x * x + y * y);
            
            // Calculate ripple height
            // We use a sine wave that radiates outward
            const z = Math.sin(d * 1.5 - time * rippleSpeed) * rippleIntensity * Math.exp(-d * 0.1);
            
            positions[i + 2] = z;
        }
        
        meshRef.current.geometry.attributes.position.needsUpdate = true;
    });

    return (
        <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} position={[0, -1, 0]}>
            <planeGeometry args={[size, size, divisions, divisions]} />
            <meshBasicMaterial 
                color="#00ffcc" 
                wireframe 
                transparent 
                opacity={0.3} 
                blending={THREE.AdditiveBlending}
            />
        </mesh>
    );
};

export default RadarGrid;
