from collections.abc import Sequence

import numpy as np
from mathutils import Matrix, Vector


def get_unique_value_indices_map(array: np.ndarray) -> dict[float, list[int]]:
    """用来获取相同权重的顶点索引列表的过程比较消耗性能,直接用blender对所有顶点赋予权重会更快(不管权重是否相同)"""
    unique_values = np.unique(array)
    return {value: np.where(array == value)[0].tolist() for value in unique_values}


def vecs_apply_mat(
    vecs: list[Vector] | list[np.ndarray] | np.ndarray,
    matrix: Matrix,
) -> np.ndarray:
    """向量应用矩阵结果等于向量左乘矩阵
    矩阵乘法满足(A @ B).T == B.T @ A.T,即A @ B == (B.T @ A.T).T
    所以,变换后的列坐标=列坐标左乘世界矩阵,等效于,变换后的行坐标=行坐标右乘世界矩阵转置"""
    return (
        np.hstack((np.asarray(vecs), np.ones((len(vecs), 1)))) @ np.asarray(matrix).T
    )[:, :3]


def compute_angle(
    vector1: Sequence[float] | Vector | np.ndarray,
    vector2: Sequence[float] | Vector | np.ndarray,
    acute: bool = False,
) -> float:
    arr1 = np.asarray(vector1)
    arr2 = np.asarray(vector2)

    dot_product = np.dot(arr1, arr2)
    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)
    cos_angle = dot_product / (norm1 * norm2)

    angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))

    if acute:
        if (np.cross(arr1, arr2) < 0).any():
            angle *= -1

        if angle < -np.pi / 2:
            angle += np.pi
        elif angle > np.pi / 2:
            angle -= np.pi

    return angle
