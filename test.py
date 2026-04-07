class Dog:
    # 1. 初始化方法 (建構子)
    def __init__(self, name):
        self.name = name  # 這是狗狗的屬性（名字）

    # 2. 方法 (行為)
    def bark(self):
        print( "汪汪")

# 使用這個類別來創建一隻狗
dog1 = Dog("小黑")
dog1.bark()  # 輸出: 小黑 汪汪