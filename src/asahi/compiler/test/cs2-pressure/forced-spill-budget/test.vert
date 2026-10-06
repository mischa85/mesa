#version 450
layout(location=0) out vec4 coords;
void main(){float x=float(gl_VertexIndex);gl_Position=vec4(x,0,0,1);coords=vec4(x,x+0.1,x+0.2,x+0.3);}
